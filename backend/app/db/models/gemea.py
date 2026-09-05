from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TwinQuestion(Base):
    """Questão gêmea gerada por IA a partir de uma questão base (spec §2).
    A IA cria enunciado, alternativas E gabarito — é a autoridade da PRÓPRIA
    gêmea (não da questão oficial). Conta para Mastery, não para a nota oficial."""

    __tablename__ = "twin_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    origin_question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    enunciado: Mapped[str] = mapped_column(Text)
    alternativas: Mapped[dict] = mapped_column(JSONB, default=dict)  # {A: "...", ...}
    gabarito: Mapped[str] = mapped_column(String(1))
    modelo: Mapped[str] = mapped_column(String(200), default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
