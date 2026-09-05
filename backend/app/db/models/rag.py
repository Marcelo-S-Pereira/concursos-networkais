from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# dimensão do modelo de embeddings (multilingual-e5-large-instruct = 1024).
# Trocar o modelo exige nova migration (a dimensão é fixa na coluna).
DIM_EMBEDDING = 1024


class RagDocument(Base):
    """Um documento da biblioteca RAG (edital, norma, apostila...). O arquivo
    original fica fora do git; aqui mora o texto e os metadados."""

    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(300))
    colecao: Mapped[str] = mapped_column(String(60), default="oficial", index=True)  # oficial|cursinho|...
    origem: Mapped[str] = mapped_column(String(500), default="")  # caminho/URL de referência
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    indexado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    erro: Mapped[str | None] = mapped_column(String(500), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["RagChunk"]] = relationship(back_populates="documento", cascade="all, delete-orphan")


class RagChunk(Base):
    """Um pedaço do documento, com seu embedding no pgvector. Busca por distância
    de cosseno (ORDER BY embedding <=> query)."""

    __tablename__ = "rag_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("rag_documents.id", ondelete="CASCADE"), index=True)
    colecao: Mapped[str] = mapped_column(String(60), index=True)  # denormalizado p/ filtrar sem join
    chunk_index: Mapped[int] = mapped_column(Integer)
    conteudo: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(DIM_EMBEDDING), nullable=True)

    documento: Mapped[RagDocument] = relationship(back_populates="chunks")
