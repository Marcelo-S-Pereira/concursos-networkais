"""[115]: Chat de estudo — múltiplos cadernos e modo aleatório de questão.
`conversations.exam_ids` guarda a lista de cadernos escolhidos (vazio = sem
caderno específico, ou lê `exam_id` singular pra conversas antigas —
retrocompatível, tratado em código). `modo_questao` ("normal"|"random")
decide se o aluno escolhe a questão ou se o backend sorteia.

Revision ID: 0039_chat_multi_caderno
Revises: 0038_tutor_selecao_conhecimento
"""

import sqlalchemy as sa

from alembic import op

revision = "0039_chat_multi_caderno"
down_revision = "0038_tutor_selecao_conhecimento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("exam_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "conversations",
        sa.Column("modo_questao", sa.String(length=10), nullable=False, server_default="normal"),
    )


def downgrade() -> None:
    op.drop_column("conversations", "modo_questao")
    op.drop_column("conversations", "exam_ids")
