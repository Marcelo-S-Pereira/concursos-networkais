"""Coluna pagina na questão (página do PDF de origem).

Revision ID: 0006_questao_pagina
Revises: 0005_questoes
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_questao_pagina"
down_revision = "0005_questoes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("pagina", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("questions", "pagina")
