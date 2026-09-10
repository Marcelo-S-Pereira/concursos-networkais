from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class YoutubeConfig(Base):
    """Chave da YouTube Data API v3 — uma única, global (não é por usuário nem
    por plataforma). Cifrada no mesmo molde da conexão de IA e do pagamento."""

    __tablename__ = "youtube_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    chave_cifrada: Mapped[str] = mapped_column(String(1000))  # AES-256-GCM

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
