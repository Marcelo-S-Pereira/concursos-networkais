"""Tutor IA ([109]), 1º incremento: `conversations.modo` (chat|tutor) e
`persona` (professor|amigo) reaproveitam a mesma tabela de conversas do chat
de estudo — mesmo pipeline de crédito/voz/modelo, só muda o system prompt e
o filtro de RAG. `rag_documents.enviado_por_user_id` guarda quem contribuiu
com PDF/vídeo (null = admin/import original), pra aparecer na Biblioteca.

Revision ID: 0037_tutor_ia
Revises: 0036_rag_descricao
"""

import sqlalchemy as sa

from alembic import op

revision = "0037_tutor_ia"
down_revision = "0036_rag_descricao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("modo", sa.String(length=10), nullable=False, server_default="chat"))
    op.add_column(
        "conversations", sa.Column("persona", sa.String(length=10), nullable=False, server_default="professor")
    )
    op.add_column("rag_documents", sa.Column("enviado_por_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_rag_documents_enviado_por", "rag_documents", "users", ["enviado_por_user_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_rag_documents_enviado_por", "rag_documents", type_="foreignkey")
    op.drop_column("rag_documents", "enviado_por_user_id")
    op.drop_column("conversations", "persona")
    op.drop_column("conversations", "modo")
