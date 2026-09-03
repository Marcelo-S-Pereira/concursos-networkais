"""Estatística pública por ênfase.

Revision ID: 0008_emphasis_stats
Revises: 0007_simulado
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_emphasis_stats"
down_revision = "0007_simulado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emphasis_public_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("banca", sa.String(80), nullable=False, server_default=""),
        sa.Column("orgao", sa.String(120), nullable=False, server_default=""),
        sa.Column("cargo", sa.String(160), nullable=False, server_default=""),
        sa.Column("ano", sa.Integer(), nullable=True),
        sa.Column("enfase", sa.String(120), nullable=False),
        sa.Column("amostra", sa.Integer(), nullable=True),
        sa.Column("acerto_pct", sa.Float(), nullable=True),
        sa.Column("fonte", sa.String(300), nullable=False, server_default=""),
        sa.Column("tipo_fonte", sa.String(60), nullable=False, server_default=""),
        sa.Column("status", sa.String(30), nullable=False, server_default="OK"),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_emphasis_public_stats_enfase", "emphasis_public_stats", ["enfase"])


def downgrade() -> None:
    op.drop_table("emphasis_public_stats")
