"""Tutor IA (spec §3,4,16,18). O LLM só explica — o backend já decidiu certo/
errado. Devolve diagnóstico, mini-aula, macete e tipo de erro, e persiste."""

import json

from sqlalchemy.orm import Session

from app.db.models import LlmTeachingOutput, Question
from app.modules.ai_registry import resolver, servico
from app.modules.ingestion.transcricao_ia import _parse_json_tolerante

TIPOS_ERRO = {
    "CONCEPT", "CALCULATION", "INTERPRETATION", "MEMORY", "UNIT_CONVERSION",
    "CONFUSION_BETWEEN_CONCEPTS", "LIKELY_GUESS", "TIME_PRESSURE", "NONE",
}

SISTEMA = (
    "Você é um tutor de concursos. Explica de forma curta e correta. Você NÃO decide "
    "certo/errado (isso já veio do backend). NUNCA invente estatística, nota, percentual "
    "de candidatos ou dificuldade. Devolva SOMENTE um JSON válido no formato: "
    '{"diagnosis": "...", "mini_lesson": "...", '
    '"memory_trick": {"memory_hook": "...", "rapid_rule": "...", "steps": ["..."], '
    '"applies_when": "...", "warning": "..."}, '
    '"error_type": "CONCEPT|CALCULATION|INTERPRETATION|MEMORY|UNIT_CONVERSION|'
    'CONFUSION_BETWEEN_CONCEPTS|LIKELY_GUESS|TIME_PRESSURE|NONE", '
    '"review_recommendation": "..."}. mini_lesson curta (5 a 15 linhas).'
)


def explicar_questao(db: Session, questao: Question, user_id: int, student_answer: str | None) -> dict:
    alternativas = "\n".join(f"({c.letra}) {c.texto}" for c in questao.alternativas)
    correto = bool(student_answer and questao.gabarito and student_answer.upper() == questao.gabarito)

    prompt = (
        f"Disciplina: {questao.disciplina}\n"
        f"Enunciado: {questao.enunciado}\n"
        f"Alternativas:\n{alternativas}\n"
        f"Resposta oficial (gabarito do backend): {questao.gabarito}\n"
        f"Resposta do aluno: {student_answer or 'em branco'}\n"
        f"O aluno {'acertou' if correto else 'errou'}.\n"
        "Explique o conceito, diagnostique o provável erro (se errou), dê um macete correto "
        "e diga o que revisar."
    )
    mensagens = [{"role": "system", "content": SISTEMA}, {"role": "user", "content": prompt}]
    resposta = servico.conversar(db, "texto", mensagens, origem="tutor_explica", max_tokens=1500)
    dados = _parse_json_tolerante(resposta)

    trick = dados.get("memory_trick") or {}
    error_type = str(dados.get("error_type", "NONE")).upper()
    if error_type not in TIPOS_ERRO:
        error_type = "NONE"

    saida = {
        "diagnosis": str(dados.get("diagnosis", "")).strip(),
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
