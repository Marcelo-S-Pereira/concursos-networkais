from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CreditTransaction(Base):
    """Lançamento na carteira de créditos do usuário. Saldo = soma dos delta.

    delta > 0 = ganho (compra, bônus, ajuste); delta < 0 = gasto (simulado, chat).
    """

    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    # compra | bonus | ajuste | gasto_simulado | gasto_chat_texto | gasto_chat_voz
    tipo: Mapped[str] = mapped_column(String(30))
    descricao: Mapped[str] = mapped_column(String(200), default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
