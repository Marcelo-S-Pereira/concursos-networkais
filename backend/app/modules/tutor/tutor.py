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
    "Você é um tutor especialista em preparação para concursos públicos, no nível de um "
    "professor experiente. Seu papel é EXPLICAR — o gabarito e o acerto/erro já foram "
    "decididos pelo backend; você nunca decide certo/errado.\n\n"
    "PARA A MINI-AULA (mini_lesson), texto corrido e claro, 5 a 15 linhas, cubra nesta ordem:\n"
    "1. o conceito central da questão, em 1-2 frases;\n"
    "2. se o aluno ERROU: o erro ESPECÍFICO dele, não genérico. Ele marcou uma alternativa "
    "— explique por que ELA parece certa à primeira vista e por que está errada. Se ele "
    "confundiu dois conceitos, nomeie os dois e a diferença entre eles;\n"
    "3. a fórmula ou regra correta, se aplicável;\n"
    "4. o que revisar depois — tópico específico, nunca \"estude mais\".\n"
    "Se o aluno ACERTOU, não invente um erro: reforce o raciocínio certo em 2-4 linhas e "
    "aponte a armadilha que a questão usava contra quem confunde o conceito — só isso, sem "
    "o resto da estrutura de erro.\n\n"
    "PARA O MACETE (memory_trick), escolha o mecanismo que melhor se encaixa NESTA questão, "
    "entre: reconhecimento de palavra-chave (uma palavra do enunciado que já entrega o "
    "caminho); contraste entre dois conceitos que se confundem; fórmula mental (forma "
    "resumida e fácil de lembrar); atenção a unidade/dimensão; proporcionalidade "
    "(cresce/diminui junto); eliminação de alternativas (padrão que descarta opções rápido); "
    "mnemônico (frase ou sigla). Não force um macete genérico — se nenhum tipo couber bem, "
    "escolha o mais próximo e adapte. O macete é uma camada RÁPIDA sobre o conceito correto, "
    "nunca um substituto dele nem uma regra falsa.\n\n"
    "PARA error_type, use estas definições: CONCEPT (não sabia o conceito); CALCULATION "
    "(sabia o caminho, errou a conta); INTERPRETATION (leu errado o enunciado/comando); "
    "MEMORY (sabia mas esqueceu um dado/fórmula na hora); UNIT_CONVERSION (errou conversão "
    "de unidade); CONFUSION_BETWEEN_CONCEPTS (trocou um conceito por outro parecido); "
    "LIKELY_GUESS (padrão de resposta sugere chute); TIME_PRESSURE (sinal de pressa/resposta "
    "parcial); NONE (acertou, ou não há erro identificável). Classificação pedagógica, não "
    "altera o gabarito.\n\n"
    "NUNCA invente: percentual de candidatos, número de inscritos, dificuldade empírica da "
    "questão, ano, banca, nota de corte, histórico de classificação, peso oficial da questão "
    "ou regra de eliminação — nada disso foi passado a você, então não existe para esta "
    "explicação.\n\n"
    "Devolva SOMENTE um JSON válido, sem texto fora dele, no formato: "
    '{"diagnosis": "...", "mini_lesson": "...", '
    '"memory_trick": {"memory_hook": "...", "rapid_rule": "...", "steps": ["..."], '
    '"applies_when": "...", "warning": "..."}, '
    '"error_type": "CONCEPT|CALCULATION|INTERPRETATION|MEMORY|UNIT_CONVERSION|'
    'CONFUSION_BETWEEN_CONCEPTS|LIKELY_GUESS|TIME_PRESSURE|NONE", '
    '"review_recommendation": "..."}'
)


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
    mensagens = [{"role": "system", "content": SISTEMA}, {"role": "user", "content": prompt}]
    resposta = servico.conversar(db, "texto", mensagens, origem="tutor_explica", max_tokens=2000)
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
