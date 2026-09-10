from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FeatureGrant(Base):
    """Quem pode usar qual recurso restrito, e quantas vezes por dia.

    Recurso restrito = coisa com consumo/custo (busca no YouTube, e no futuro
    outras) que não é liberada globalmente ao comprar crédito — o admin decide
    pessoa por pessoa, conforme uso/compra. Sem linha aqui = sem acesso
    (exceto superadmin, que sempre tem, ver `modules/features/features.py`).
    """

    __tablename__ = "feature_grants"
    __table_args__ = (UniqueConstraint("user_id", "feature", name="uq_feature_grants_user_feature"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    feature: Mapped[str] = mapped_column(String(40))
    limite_diario: Mapped[int] = mapped_column(Integer, default=5)
    concedido_por: Mapped[int | None] = mapped_column(Integer, nullable=True)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class ResourceUsageLog(Base):
    """Uma linha por uso real de um recurso restrito — é a partir daqui que se
    sabe quanto cada um já gastou hoje. Mesmo molde do `AiCallLog`."""

    __tablename__ = "resource_usage_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    feature: Mapped[str] = mapped_column(String(40), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
