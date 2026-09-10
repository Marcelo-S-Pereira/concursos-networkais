"""Saídas do tutor IA: llm_teaching_outputs.

Revision ID: 0010_tutor
Revises: 0009_modo_exibicao
"""

import sqlalchemy as sa

from alembic import op

revision = "0010_tutor"
down_revision = "0009_modo_exibicao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_teaching_outputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("student_answer", sa.String(1), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("diagnosis", sa.Text(), nullable=False, server_default=""),
        sa.Column("mini_lesson", sa.Text(), nullable=False, server_default=""),
        sa.Column("memory_trick", sa.Text(), nullable=False, server_default=""),
        sa.Column("error_type", sa.String(40), nullable=False, server_default=""),
        sa.Column("review_recommendation", sa.Text(), nullable=False, server_default=""),
        sa.Column("modelo", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_llm_teaching_outputs_question_id", "llm_teaching_outputs", ["question_id"])
    op.create_index("ix_llm_teaching_outputs_user_id", "llm_teaching_outputs", ["user_id"])


def downgrade() -> None:
    op.drop_table("llm_teaching_outputs")
