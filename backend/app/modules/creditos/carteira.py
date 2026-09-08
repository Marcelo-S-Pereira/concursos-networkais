"""Carteira de créditos: lançar e resumir. Saldo = soma dos delta."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CreditTransaction


def creditar(db: Session, user_id: int, delta: int, tipo: str, descricao: str = "") -> None:
    db.add(CreditTransaction(user_id=user_id, delta=delta, tipo=tipo, descricao=descricao[:200]))
    db.commit()


def creditar_lote(db: Session, user_ids: list[int], delta: int, tipo: str, descricao: str = "") -> int:
    """Credita vários usuários de uma vez (1 commit). Devolve quantos foram creditados."""
    for uid in user_ids:
        db.add(CreditTransaction(user_id=uid, delta=delta, tipo=tipo, descricao=descricao[:200]))
    db.commit()
    return len(user_ids)


def saldo(db: Session, user_id: int) -> int:
    txs = db.execute(select(CreditTransaction.delta).where(CreditTransaction.user_id == user_id)).scalars().all()
    return sum(txs)


def resumo(db: Session, user_id: int) -> dict:
    txs = list(
        db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user_id)
            .order_by(CreditTransaction.criado_em.desc())
        ).scalars()
    )
    ganho = sum(t.delta for t in txs if t.delta > 0)
    gasto = sum(-t.delta for t in txs if t.delta < 0)
    extrato = [
        {
            "delta": t.delta, "tipo": t.tipo, "descricao": t.descricao,
            "quando": t.criado_em.isoformat() if t.criado_em else None,
        }
        for t in txs[:50]
    ]
    return {"saldo": ganho - gasto, "total_ganho": ganho, "total_gasto": gasto, "extrato": extrato}
