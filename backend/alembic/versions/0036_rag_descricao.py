"""Descrição prévia do documento RAG ([108]) — resumo do conteúdo, editável
pelo admin, pra "memória de conhecimento": saber do que trata cada documento
sem abrir o PDF de novo. Gerada como rascunho na ingestão (melhor esforço,
via LLM), nunca bloqueia o import se faltar conexão.

Revision ID: 0036_rag_descricao
Revises: 0035_rag_classificacao_uso
"""

import sqlalchemy as sa

from alembic import op

revision = "0036_rag_descricao"
down_revision = "0035_rag_classificacao_uso"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rag_documents", sa.Column("descricao", sa.String(length=500), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("rag_documents", "descricao")
