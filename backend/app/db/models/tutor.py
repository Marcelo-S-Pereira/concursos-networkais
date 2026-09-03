from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LlmTeachingOutput(Base):
    """Saída pedagógica do tutor (spec §20). O LLM gera pedagogia; o backend já
    tem a verdade. Guardado para reconstruir sem chamar o LLM de novo."""

    __tablename__ = "llm_teaching_outputs"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    student_answer: Mapped[str | None] = mapped_column(String(1), nullable=True)
    correct: Mapped[bool] = mapped_column(Boolean, default=False)
    diagnosis: Mapped[str] = mapped_column(Text, default="")
    mini_lesson: Mapped[str] = mapped_column(Text, default="")
    memory_trick: Mapped[str] = mapped_column(Text, default="")  # JSON serializado
    error_type: Mapped[str] = mapped_column(String(40), default="")
    review_recommendation: Mapped[str] = mapped_column(Text, default="")
    modelo: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
