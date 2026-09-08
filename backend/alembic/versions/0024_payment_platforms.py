"""Plataformas de pagamento (Mercado Pago, Stripe...): credencial cifrada.

Revision ID: 0024_payment_platforms
Revises: 0023_system_settings
"""

import sqlalchemy as sa

from alembic import op

revision = "0024_payment_platforms"
down_revision = "0023_system_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_platforms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("titulo", sa.String(length=120), nullable=False),
        sa.Column("provedor", sa.String(length=30), nullable=False, server_default="mercadopago"),
        sa.Column("access_token_cifrado", sa.String(length=1000), nullable=False),
        sa.Column("public_key", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_payment_platforms_provedor", "payment_platforms", ["provedor"])


def downgrade() -> None:
    op.drop_index("ix_payment_platforms_provedor", table_name="payment_platforms")
    op.drop_table("payment_platforms")
