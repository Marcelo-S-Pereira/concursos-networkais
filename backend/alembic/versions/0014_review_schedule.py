"""Revisão espaçada: review_schedule.

Revision ID: 0014_review_schedule
Revises: 0013_exam_rules
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_review_schedule"
down_revision = "0013_exam_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_schedule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("intervalo_idx", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vence_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ultimo_resultado", sa.String(8), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "question_id", name="uq_review_user_question"),
    )
    op.create_index("ix_review_schedule_user_id", "review_schedule", ["user_id"])
    op.create_index("ix_review_schedule_question_id", "review_schedule", ["question_id"])
    op.create_index("ix_review_schedule_vence_em", "review_schedule", ["vence_em"])


def downgrade() -> None:
    op.drop_table("review_schedule")
