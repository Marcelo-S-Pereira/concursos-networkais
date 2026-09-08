"""Tabela system_settings (chave→valor): ex. cadastros_bloqueados.

Revision ID: 0023_system_settings
Revises: 0022_pergunta_questao
"""

import sqlalchemy as sa

from alembic import op

revision = "0023_system_settings"
down_revision = "0022_pergunta_questao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("chave", sa.String(length=60), primary_key=True),
        sa.Column("valor", sa.String(length=200), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
