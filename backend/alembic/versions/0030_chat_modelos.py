"""Escolha da IA por conversa: qual modelo atende texto e qual atende imagem.

Nullable = "deixa o motor resolver pela categoria ativa", que é o que já
acontecia. Só quem escolher explicitamente sai do padrão.

Revision ID: 0030_chat_modelos
Revises: 0029_ai_call_log_user
"""

import sqlalchemy as sa

from alembic import op

revision = "0030_chat_modelos"
down_revision = "0029_ai_call_log_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("modelo_texto_id", sa.Integer(), nullable=True))
    op.add_column("conversations", sa.Column("modelo_visao_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "modelo_visao_id")
    op.drop_column("conversations", "modelo_texto_id")
