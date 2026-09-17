from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FilaHistorico(Base):
    """[126]: amostra periódica (mesmo ritmo do monitor de saúde, [068] —
    3 em 3 min, 1 única tarefa de fundo) de carga da ambiente de execucao + estado da fila de
    admissão de chamadas de IA. Histórico persistido para o admin decidir
    quando escalar o servidor a partir de tendência real, não só do
    instantâneo."""

    __tablename__ = "fila_historico"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cpu_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    memoria_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    disco_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    em_voo: Mapped[int] = mapped_column(Integer, default=0)
    esperando: Mapped[int] = mapped_column(Integer, default=0)
    max_concorrente: Mapped[int] = mapped_column(Integer, default=0)
    admitidas: Mapped[int] = mapped_column(Integer, default=0)
    rejeitadas: Mapped[int] = mapped_column(Integer, default=0)
    espera_media_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
