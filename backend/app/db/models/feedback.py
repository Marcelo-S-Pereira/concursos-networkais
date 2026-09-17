from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Feedback(Base):
    """[153]: feedback de uma ferramenta (Chat de estudo/Tutor IA/Simulado) —
    estrelas + texto, opcionais (pode mandar só um dos dois). Ao ser criado,
    dispara um e-mail pro dono (`enviar_email`, best-effort — a linha fica
    salva mesmo se o e-mail falhar)."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ferramenta: Mapped[str] = mapped_column(String(20), index=True)  # chat | tutor_ia | simulado
    estrelas: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
