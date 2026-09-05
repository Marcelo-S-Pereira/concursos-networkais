from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CatalogPlatform(Base):
    """Catálogo de plataformas conhecidas (Together, OpenAI, ...). Fica no banco
    para ser editável sem tocar em código."""

    __tablename__ = "ai_catalog_platform"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True)
    endpoint: Mapped[str] = mapped_column(String(500))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CatalogModel(Base):
    """Catálogo de modelos por plataforma+categoria, para o usuário escolher em
    lista. Carregado do banco — nada chumbado no front/back."""

    __tablename__ = "ai_catalog_model"
    __table_args__ = (UniqueConstraint("plataforma", "categoria", "model_id", name="uq_catalog_model"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plataforma: Mapped[str] = mapped_column(String(80), index=True)  # casa com CatalogPlatform.nome
    categoria: Mapped[str] = mapped_column(String(20), index=True)   # texto|visao|embeddings|transcricao|voz
    model_id: Mapped[str] = mapped_column(String(200))              # o "model" da chamada
    rotulo: Mapped[str] = mapped_column(String(200), default="")     # nota curta p/ exibir
    dim: Mapped[int | None] = mapped_column(Integer, nullable=True)  # dimensão (embeddings)
    padrao: Mapped[bool] = mapped_column(Boolean, default=False)     # sugerido por padrão
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
