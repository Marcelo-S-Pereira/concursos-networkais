"""Tutor IA (spec §3,4,16,18). O LLM só explica — o backend já decidiu certo/
errado. Devolve diagnóstico, mini-aula, macete e tipo de erro, e persiste."""

import json

from sqlalchemy.orm import Session

from app.db.models import LlmTeachingOutput, Question
from app.modules.ai_registry import resolver, servico
from app.modules.ingestion.transcricao_ia import _parse_json_tolerante
from app.modules.prompts import prompts
from app.modules.rag.rag import contexto_biblioteca

TIPOS_ERRO = {
    "CONCEPT", "CALCULATION", "INTERPRETATION", "MEMORY", "UNIT_CONVERSION",
    "CONFUSION_BETWEEN_CONCEPTS", "LIKELY_GUESS", "TIME_PRESSURE", "NONE",
}

# [125]: texto em `prompts` (chave "tutor_explicar_sistema"), não mais aqui.


def explicar_questao(db: Session, questao: Question, user_id: int, student_answer: str | None) -> dict:
    alternativas = "\n".join(f"({c.letra}) {c.texto}" for c in questao.alternativas)
    correto = bool(student_answer and questao.gabarito and student_answer.upper() == questao.gabarito)

    # Manda o TEXTO das alternativas, não só a letra — é o que permite ao LLM
    # explicar por que a errada parecia certa, em vez de reensinar o conceito no vácuo.
    letra_aluno = (student_answer or "").upper()
    texto_escolhida = next((c.texto for c in questao.alternativas if c.letra == letra_aluno), None)
    texto_correta = next((c.texto for c in questao.alternativas if c.letra == questao.gabarito), None)

    prompt = (
        f"Disciplina: {questao.disciplina}\n"
        f"Enunciado: {questao.enunciado}\n"
        f"Alternativas:\n{alternativas}\n"
        f"Resposta oficial (gabarito do backend): {questao.gabarito}"
        + (f' — "{texto_correta}"' if texto_correta else "") + "\n"
        f"Resposta do aluno: {student_answer or 'em branco'}"
        + (f' — "{texto_escolhida}"' if texto_escolhida else "") + "\n"
        f"O aluno {'acertou' if correto else 'errou'}.\n"
        "Monte a mini-aula e o macete seguindo exatamente as instruções do sistema para "
        "este caso (acertou ou errou)."
    )
    # [114]: material que o admin classificou pra "Simulado" na Biblioteca —
    # só entra se ele mesmo marcou como pertinente; best-effort, nunca lança.
    sistema = prompts.buscar(db, "tutor_explicar_sistema")
    biblioteca = contexto_biblioteca(db, f"{questao.disciplina} {questao.enunciado}", uso="simulado")
    if biblioteca:
        sistema += "\n\n" + biblioteca

    mensagens = [{"role": "system", "content": sistema}, {"role": "user", "content": prompt}]
    resposta = servico.conversar(db, "texto", mensagens, origem="tutor_explica", max_tokens=2000)
    # [achado ao testar o fix de asterisco]: em questões de cálculo difíceis o
    # LLM às vezes entra num loop de "revisar de novo" ([086]/[117], limite
    # conhecido do modelo) e estoura max_tokens no meio do JSON — o parse
    # falha (JSONDecodeError/ValueError). Sem isso, a rota crashava (500) pro
    # aluno em vez de devolver uma mensagem honesta.
    try:
        dados = _parse_json_tolerante(resposta)
    except (json.JSONDecodeError, ValueError):
        dados = {}

    trick = dados.get("memory_trick") or {}
    error_type = str(dados.get("error_type", "NONE")).upper()
    if error_type not in TIPOS_ERRO:
        error_type = "NONE"

    diagnosis = str(dados.get("diagnosis", "")).strip()
    if not diagnosis and not dados:
        diagnosis = "Não consegui montar a explicação desta vez — tente de novo."

    saida = {
        "diagnosis": diagnosis,
        "mini_lesson": str(dados.get("mini_lesson", "")).strip(),
        "memory_trick": {
            "memory_hook": str(trick.get("memory_hook", "")).strip(),
            "rapid_rule": str(trick.get("rapid_rule", "")).strip(),
            "steps": [str(s).strip() for s in (trick.get("steps") or []) if str(s).strip()],
            "applies_when": str(trick.get("applies_when", "")).strip(),
            "warning": str(trick.get("warning", "")).strip(),
        },
        "error_type": error_type,
        "review_recommendation": str(dados.get("review_recommendation", "")).strip(),
        "correct": correto,
    }

    # persiste (spec §20) — best-effort, não derruba a resposta
    try:
        conn = resolver.cadeia_para_categoria(db, "texto")
        db.add(LlmTeachingOutput(
            question_id=questao.id, user_id=user_id, student_answer=student_answer,
            correct=correto, diagnosis=saida["diagnosis"], mini_lesson=saida["mini_lesson"],
            memory_trick=json.dumps(saida["memory_trick"], ensure_ascii=False),
            error_type=error_type, review_recommendation=saida["review_recommendation"],
            modelo=conn[0].modelo if conn else "",
        ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()

    return saida


# [117]/[125]: Tutor por voz guiado — narra a resolução em PASSOS curtos, um
# de cada vez, pra tocar em áudio e o aluno acompanhar (botão ou voz avançam).
# Texto em `prompts` (chave "tutor_passo_a_passo_sistema"), não mais aqui.


def gerar_passo_a_passo(db: Session, questao: Question, user_id: int) -> list[str]:
    alternativas = "\n".join(f"({c.letra}) {c.texto}" for c in questao.alternativas)
    texto_correta = next((c.texto for c in questao.alternativas if c.letra == questao.gabarito), None)
    prompt = (
        f"Disciplina: {questao.disciplina}\n"
        f"Enunciado: {questao.enunciado}\n"
        f"Alternativas:\n{alternativas}\n"
        f"Resposta correta (gabarito do backend): {questao.gabarito}"
        + (f' — "{texto_correta}"' if texto_correta else "") + "\n"
        "Narre a resolução completa em passos curtos, conforme as instruções do sistema."
    )
    mensagens = [{"role": "system", "content": prompts.buscar(db, "tutor_passo_a_passo_sistema")},
                 {"role": "user", "content": prompt}]
    resposta = servico.conversar(db, "texto", mensagens, origem="tutor_passo_a_passo", max_tokens=1500,
                                 user_id=user_id)
    # mesmo achado do explicar_questao: questão de cálculo difícil pode fazer
    # o LLM entrar num loop de "revisar de novo" e estourar max_tokens no
    # meio do JSON — cai no fallback abaixo em vez de derrubar a rota (500).
    try:
        dados = _parse_json_tolerante(resposta)
    except (json.JSONDecodeError, ValueError):
        dados = {}
    passos = [str(p).strip() for p in (dados.get("passos") or []) if str(p).strip()]
    if not passos:
        passos = ["Não consegui montar os passos desta questão — tente 'Explicar' ou 'Mini-aula' em vez disso."]
    return passos[:10]  # teto de segurança contra resposta anormalmente longa
