"""Regras do edital por caderno: exam_rules.

Revision ID: 0013_exam_rules
Revises: 0012_ai_platforms
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013_exam_rules"
down_revision = "0012_ai_platforms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exam_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exam_id", sa.Integer(), sa.ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("pesos", JSONB(), nullable=False, server_default="{}"),
        sa.Column("minimos", JSONB(), nullable=False, server_default="{}"),
        sa.Column("nota_corte", sa.Float(), nullable=True),
        sa.Column("vagas", sa.Integer(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_exam_rules_exam_id", "exam_rules", ["exam_id"], unique=True)


def downgrade() -> None:
    op.drop_table("exam_rules")
