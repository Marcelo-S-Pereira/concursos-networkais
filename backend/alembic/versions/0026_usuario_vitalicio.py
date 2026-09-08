"""Acesso vitalício por usuário (não consome créditos).

Revision ID: 0026_usuario_vitalicio
Revises: 0025_credit_transactions
"""

import sqlalchemy as sa

from alembic import op

revision = "0026_usuario_vitalicio"
down_revision = "0025_credit_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("vitalicio", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "vitalicio")
