"""Modo de exibição da questão no simulado: texto ou imagem (print).

Revision ID: 0009_modo_exibicao
Revises: 0008_emphasis_stats
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_modo_exibicao"
down_revision = "0008_emphasis_stats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("modo_exibicao", sa.String(10), nullable=False, server_default="texto"))


def downgrade() -> None:
    op.drop_column("questions", "modo_exibicao")
