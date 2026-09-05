"""Geração de questões gêmeas por IA (spec §2). A IA cria enunciado, alternativas
e gabarito — é a autoridade das próprias gêmeas."""

from sqlalchemy.orm import Session

from app.db.models import Question, TwinQuestion
from app.modules.ai_registry import resolver, servico
from app.modules.ingestion.transcricao_ia import _parse_json_tolerante

SISTEMA = (
    "Você gera DUAS questões gêmeas de concurso a partir de uma questão base: mesma "
    "habilidade/conceito, contexto DIFERENTE, sem copiar a base, com resposta única e "
    "correta. Faça a primeira equivalente e a segunda com uma pequena variação. Devolva "
    "SOMENTE JSON válido: "
    '{"gemeas": [{"enunciado": "...", "alternativas": {"A": "...", "B": "...", "C": "...", '
    '"D": "...", "E": "..."}, "gabarito": "A"}, {"enunciado": "...", "alternativas": {...}, '
    '"gabarito": "B"}]}'
)


def gerar_gemeas(db: Session, questao: Question, user_id: int) -> list[dict]:
    alternativas = "\n".join(f"({c.letra}) {c.texto}" for c in questao.alternativas)
    prompt = (
        f"Disciplina: {questao.disciplina}\nQuestão base:\n{questao.enunciado}\n{alternativas}\n"
        f"Gabarito da base: {questao.gabarito}\nGere as duas gêmeas."
    )
    mensagens = [{"role": "system", "content": SISTEMA}, {"role": "user", "content": prompt}]
    resposta = servico.conversar(db, "texto", mensagens, origem="gemeas", max_tokens=2500)
    dados = _parse_json_tolerante(resposta)

    conn = resolver.cadeia_para_categoria(db, "texto")
    modelo = conn[0].modelo if conn else ""
    saida = []
    for g in (dados.get("gemeas") or [])[:2]:
        alts = {L: str((g.get("alternativas") or {}).get(L, "")).strip() for L in "ABCDE"}
        gab = str(g.get("gabarito", "")).strip().upper()
        if gab not in "ABCDE" or not str(g.get("enunciado", "")).strip():
            continue
        tw = TwinQuestion(
            origin_question_id=questao.id, user_id=user_id,
            enunciado=str(g["enunciado"]).strip(), alternativas=alts, gabarito=gab, modelo=modelo,
        )
        db.add(tw)
        db.flush()
        # não expõe o gabarito ao devolver — o aluno responde primeiro
        saida.append({"id": tw.id, "enunciado": tw.enunciado, "alternativas": alts})
    db.commit()
    return saida
