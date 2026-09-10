"""Segunda coluna do enunciado (edição em duas colunas).

Revision ID: 0011_enunciado_col2
Revises: 0010_tutor
"""

import sqlalchemy as sa

from alembic import op

revision = "0011_enunciado_col2"
down_revision = "0010_tutor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("enunciado_col2", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("questions", "enunciado_col2")
