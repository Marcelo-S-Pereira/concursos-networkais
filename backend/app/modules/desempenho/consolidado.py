"""Desempenho consolidado do usuário, derivado dos dados persistidos.

Tudo aqui é leitura/agregação — nada é gravado, nada é inventado. Cobre:
- Mastery consolidado (B5, §7.3): todas as respostas de simulado por disciplina.
- Dificuldade (B6, §11): taxa de erro por disciplina (proxy de dificuldade).
- Eficácia do macete (B7, §21): acerto nas revisões após receber o macete.
- Gamificação: XP, nível e streak de dias, a partir de simulados/revisões.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    LlmTeachingOutput,
    Question,
    ReviewSchedule,
    SimulationAnswer,
    SimulationRun,
)
from app.modules.desempenho.mastery import por_enfase


def _respostas(db: Session, user_id: int) -> list[tuple[str, bool]]:
    rows = db.execute(
        select(Question.disciplina, SimulationAnswer.correta)
        .join(SimulationRun, SimulationRun.id == SimulationAnswer.run_id)
        .join(Question, Question.id == SimulationAnswer.question_id)
        .where(SimulationRun.user_id == user_id, SimulationAnswer.letra.isnot(None))
    ).all()
    return [(d or "Sem classificação", bool(c)) for d, c in rows]


def mastery_consolidado(db: Session, user_id: int) -> list[dict]:
    """B5: acertos/total/%/estado de mastery por disciplina, somando todos os
    simulados do usuário."""
    return por_enfase(_respostas(db, user_id))


def _rotulo_dificuldade(erro_pct: float) -> str:
    if erro_pct >= 60:
        return "difícil"
    if erro_pct >= 35:
        return "média"
    return "fácil"


def dificuldade_por_enfase(db: Session, user_id: int) -> list[dict]:
    """B6: taxa de erro por disciplina (proxy de dificuldade)."""
    agrupado: dict[str, list[bool]] = {}
    for enfase, correta in _respostas(db, user_id):
        agrupado.setdefault(enfase, []).append(correta)
    saida = []
    for enfase, lista in sorted(agrupado.items()):
        total = len(lista)
        erros = sum(1 for c in lista if not c)
        erro_pct = round(erros / total * 100, 1) if total else 0.0
        saida.append({
            "enfase": enfase, "tentativas": total, "erros": erros,
            "erro_pct": erro_pct, "dificuldade": _rotulo_dificuldade(erro_pct),
        })
    return saida


def eficacia_macete(db: Session, user_id: int) -> dict:
    """B7: das questões em que o usuário recebeu macete, como foi o acerto nas
    revisões seguintes. Honesto quando a amostra é pequena."""
    qids_macete = {
        q for (q,) in db.execute(
            select(LlmTeachingOutput.question_id).where(LlmTeachingOutput.user_id == user_id).distinct()
        ).all()
    }
    if not qids_macete:
        return {"com_macete": 0, "revisoes_avaliadas": 0, "acerto_pos_macete_pct": None,
                "observacao": "Nenhum macete recebido ainda."}

    revisoes = db.execute(
        select(ReviewSchedule.ultimo_resultado)
        .where(ReviewSchedule.user_id == user_id,
               ReviewSchedule.question_id.in_(qids_macete),
               ReviewSchedule.ultimo_resultado.isnot(None))
    ).all()
    avaliadas = len(revisoes)
    acertos = sum(1 for (r,) in revisoes if r == "acertou")
    if avaliadas < 5:
        return {"com_macete": len(qids_macete), "revisoes_avaliadas": avaliadas,
                "acerto_pos_macete_pct": None,
                "observacao": "Aguardando dados — poucas revisões após o macete para medir."}
    return {"com_macete": len(qids_macete), "revisoes_avaliadas": avaliadas,
            "acerto_pos_macete_pct": round(acertos / avaliadas * 100, 1),
            "observacao": "Acerto nas revisões das questões em que houve macete."}


def _nivel(xp: int) -> tuple[int, int, int]:
    """Nível por faixas de 100·nível XP acumulado. Devolve (nível, xp_no_nível, xp_p/_proximo)."""
    nivel = 1
    restante = xp
    passo = 100
    while restante >= passo:
        restante -= passo
        nivel += 1
        passo = 100 * nivel
    return nivel, restante, passo


def gamificacao(db: Session, user_id: int) -> dict:
    respostas = _respostas(db, user_id)
    acertos = sum(1 for _, c in respostas if c)
    simulados = db.execute(
        select(SimulationRun.finished_at).where(
            SimulationRun.user_id == user_id, SimulationRun.status == "finished")
    ).all()
    n_simulados = len(simulados)
    revisoes = db.execute(
        select(ReviewSchedule.ultimo_resultado).where(
            ReviewSchedule.user_id == user_id, ReviewSchedule.ultimo_resultado.isnot(None))
    ).all()
    n_revisoes = len(revisoes)

    xp = acertos * 10 + n_simulados * 20 + n_revisoes * 5
    nivel, xp_no_nivel, xp_prox = _nivel(xp)

    # streak: dias consecutivos (até hoje, UTC) com simulado entregue
    dias = {s.date() for (s,) in simulados if s}
    streak = 0
    hoje = datetime.now(UTC).date()
    d: date = hoje
    while d in dias:
        streak += 1
        d = d - timedelta(days=1)

    return {
        "xp": xp, "nivel": nivel, "xp_no_nivel": xp_no_nivel, "xp_para_proximo": xp_prox,
        "acertos": acertos, "simulados": n_simulados, "revisoes": n_revisoes,
        "streak_dias": streak,
    }
