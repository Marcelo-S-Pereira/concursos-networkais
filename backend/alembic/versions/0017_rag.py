"""Biblioteca RAG no PostgreSQL/pgvector: rag_documents e rag_chunks.

Revision ID: 0017_rag
Revises: 0016_exam_rules_fases
"""

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

revision = "0017_rag"
down_revision = "0016_exam_rules_fases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "rag_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("titulo", sa.String(300), nullable=False),
        sa.Column("colecao", sa.String(60), nullable=False, server_default="oficial"),
        sa.Column("origem", sa.String(500), nullable=False, server_default=""),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("indexado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("erro", sa.String(500), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rag_documents_colecao", "rag_documents", ["colecao"])
    op.create_table(
        "rag_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("colecao", sa.String(60), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(1024), nullable=True),
    )
    op.create_index("ix_rag_chunks_document_id", "rag_chunks", ["document_id"])
    op.create_index("ix_rag_chunks_colecao", "rag_chunks", ["colecao"])


def downgrade() -> None:
    op.drop_table("rag_chunks")
    op.drop_table("rag_documents")
