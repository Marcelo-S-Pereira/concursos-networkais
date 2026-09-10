"""Questões gêmeas geradas por IA: twin_questions.

Revision ID: 0015_twin_questions
Revises: 0014_review_schedule
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0015_twin_questions"
down_revision = "0014_review_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "twin_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("origin_question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("enunciado", sa.Text(), nullable=False),
        sa.Column("alternativas", JSONB(), nullable=False, server_default="{}"),
        sa.Column("gabarito", sa.String(1), nullable=False),
        sa.Column("modelo", sa.String(200), nullable=False, server_default=""),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_twin_questions_origin_question_id", "twin_questions", ["origin_question_id"])
    op.create_index("ix_twin_questions_user_id", "twin_questions", ["user_id"])


def downgrade() -> None:
    op.drop_table("twin_questions")
