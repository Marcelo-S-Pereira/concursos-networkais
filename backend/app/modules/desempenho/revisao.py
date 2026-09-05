"""Revisão espaçada (spec §17). Intervalos em dias; acerto avança, erro reinicia."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ReviewSchedule

# escala de dias (spec §17): 1, 3, 7, 15, 30 (o índice 0 = 1 dia)
ESCALA_DIAS = [1, 3, 7, 15, 30]


def _vencimento(idx: int) -> datetime:
    dias = ESCALA_DIAS[min(idx, len(ESCALA_DIAS) - 1)]
    return datetime.now(UTC) + timedelta(days=dias)


def agendar_erro(db: Session, user_id: int, question_id: int) -> None:
    """Questão errada entra (ou reinicia) na agenda, vencendo em 1 dia."""
    r = db.execute(
        select(ReviewSchedule).where(
            ReviewSchedule.user_id == user_id, ReviewSchedule.question_id == question_id
        )
    ).scalar_one_or_none()
    if r:
        r.intervalo_idx = 0
        r.vence_em = _vencimento(0)
        r.ultimo_resultado = "errou"
    else:
        db.add(ReviewSchedule(
            user_id=user_id, question_id=question_id, intervalo_idx=0,
            vence_em=_vencimento(0), ultimo_resultado="errou",
        ))


def responder_revisao(db: Session, user_id: int, question_id: int, acertou: bool) -> None:
    r = db.execute(
        select(ReviewSchedule).where(
            ReviewSchedule.user_id == user_id, ReviewSchedule.question_id == question_id
        )
    ).scalar_one_or_none()
    if not r:
        return
    if acertou:
        r.intervalo_idx = min(r.intervalo_idx + 1, len(ESCALA_DIAS) - 1)
        r.ultimo_resultado = "acertou"
    else:
        r.intervalo_idx = 0
        r.ultimo_resultado = "errou"
    r.vence_em = _vencimento(r.intervalo_idx)
