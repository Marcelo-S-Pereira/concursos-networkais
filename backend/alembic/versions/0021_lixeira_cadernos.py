"""Soft delete de cadernos: coluna excluido_em em exams (lixeira/restaurar).

Revision ID: 0021_lixeira_cadernos
Revises: 0020_catalogo_local
"""

import sqlalchemy as sa

from alembic import op

revision = "0021_lixeira_cadernos"
down_revision = "0020_catalogo_local"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exams", sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("exams", "excluido_em")
