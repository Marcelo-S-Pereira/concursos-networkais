from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmphasisPublicStat(Base):
    """Estatística pública de acerto por ênfase (spec §9). Preenchida por
    scraping/manual. Nunca inventada: sem dado confiável, status marca isso."""

    __tablename__ = "emphasis_public_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    banca: Mapped[str] = mapped_column(String(80), default="")
    orgao: Mapped[str] = mapped_column(String(120), default="")
    cargo: Mapped[str] = mapped_column(String(160), default="")
    ano: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enfase: Mapped[str] = mapped_column(String(120), index=True)
    amostra: Mapped[int | None] = mapped_column(Integer, nullable=True)  # N de respostas
    acerto_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # % que acertam
    fonte: Mapped[str] = mapped_column(String(300), default="")
    tipo_fonte: Mapped[str] = mapped_column(String(60), default="")
    status: Mapped[str] = mapped_column(String(30), default="OK")  # OK | PUBLIC_DATA_NOT_FOUND
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
