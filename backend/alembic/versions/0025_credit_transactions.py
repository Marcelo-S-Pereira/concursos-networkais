"""Carteira de créditos: lançamentos (credit_transactions).

Revision ID: 0025_credit_transactions
Revises: 0024_payment_platforms
"""

import sqlalchemy as sa

from alembic import op

revision = "0025_credit_transactions"
down_revision = "0024_payment_platforms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("descricao", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_credit_transactions_user_id", "credit_transactions", ["user_id"])
    op.create_index("ix_credit_transactions_criado_em", "credit_transactions", ["criado_em"])


def downgrade() -> None:
    op.drop_index("ix_credit_transactions_criado_em", table_name="credit_transactions")
    op.drop_index("ix_credit_transactions_user_id", table_name="credit_transactions")
    op.drop_table("credit_transactions")
