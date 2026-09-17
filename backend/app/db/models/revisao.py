from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReviewSchedule(Base):
    """Agenda de revisão espaçada (spec §17). Uma linha por (usuário, questão).
    O intervalo avança quando acerta e reinicia quando erra."""

    __tablename__ = "review_schedule"
    __table_args__ = (UniqueConstraint("user_id", "question_id", name="uq_review_user_question"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    intervalo_idx: Mapped[int] = mapped_column(Integer, default=0)  # índice na escala de dias
    vence_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ultimo_resultado: Mapped[str | None] = mapped_column(String(8), nullable=True)  # acertou|errou
    # [153]: de onde veio a última vez que esta questão entrou/avançou na
    # agenda — "simulado" ou "chat" (respondida errado no Chat de estudos).
    origem: Mapped[str] = mapped_column(String(10), default="simulado")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
