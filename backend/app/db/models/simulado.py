from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SimulationRun(Base):
    """Uma execução de simulado por tempo. O backend é dono do relógio:
    deadline_at = started_at + duração; depois disso não aceita resposta."""

    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    question_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | finished
    acertos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    respostas: Mapped[list["SimulationAnswer"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class SimulationAnswer(Base):
    __tablename__ = "simulation_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(Integer)
    letra: Mapped[str | None] = mapped_column(String(1), nullable=True)  # None/"" = em branco
    correta: Mapped[bool] = mapped_column(default=False)
    tempo_resposta_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alteracoes: Mapped[int] = mapped_column(Integer, default=0)

    run: Mapped[SimulationRun] = relationship(back_populates="respostas")
