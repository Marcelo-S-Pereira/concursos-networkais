"""[110]: seletor de conhecimento do Tutor IA. `conversations.rag_doc_ids`
guarda quais documentos da Biblioteca (uso_tutor=true) valem pra aquela
conversa — vazio = usa todos (comportamento padrão preservado).
`rag_documents.tentativas_indexacao` conta quantas vezes tentou vetorizar,
pra mostrar "em análise" com contexto em vez de sumir sem explicação.

Revision ID: 0038_tutor_selecao_conhecimento
Revises: 0037_tutor_ia
"""

import sqlalchemy as sa

from alembic import op

revision = "0038_tutor_selecao_conhecimento"
down_revision = "0037_tutor_ia"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("rag_doc_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "rag_documents",
        sa.Column("tentativas_indexacao", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("rag_documents", "tentativas_indexacao")
    op.drop_column("conversations", "rag_doc_ids")
