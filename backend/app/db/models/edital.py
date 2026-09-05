from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExamRules(Base):
    """Regras do edital para um caderno (spec §7.1, §15). Uma linha por prova.

    O backend é a autoridade das regras: nota ponderada, mínimos por bloco,
    eliminação e nota de corte. Nada é inventado — sem regra, o resultado fica
    apenas com o percentual bruto.
    """

    __tablename__ = "exam_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), unique=True, index=True)

    # {disciplina: peso_por_questao}. Sem entrada = peso 1.0.
    pesos: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {disciplina: minimo_de_acertos}. Abaixo disso = eliminado.
    minimos: Mapped[dict] = mapped_column(JSONB, default=dict)
    # nota ponderada mínima total para não ser eliminado.
    nota_corte: Mapped[float | None] = mapped_column(Float, nullable=True)
    vagas: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Regra por FASE (edital Cesgranrio): agrupa disciplinas em fases e cobra um
    # mínimo percentual por fase, mais matérias que não podem zerar.
    fases: Mapped[dict] = mapped_column(JSONB, default=dict)  # {disciplina: fase}
    minimo_pct_fase: Mapped[dict] = mapped_column(JSONB, default=dict)  # {fase: pct}
    materias_sem_zero: Mapped[list] = mapped_column(JSONB, default=list)  # [disciplina, ...]

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
