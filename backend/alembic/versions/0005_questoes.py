"""Tabelas de questões: exams, questions, choices.

Revision ID: 0005_questoes
Revises: 0004_ai_registry
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_questoes"
down_revision = "0004_ai_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("banca", sa.String(80), nullable=False),
        sa.Column("orgao", sa.String(120), nullable=False),
        sa.Column("cargo", sa.String(160), nullable=False),
        sa.Column("ano", sa.Integer(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exam_id", sa.Integer(), sa.ForeignKey("exams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("disciplina", sa.String(60), nullable=False, server_default=""),
        sa.Column("enunciado", sa.Text(), nullable=False),
        sa.Column("gabarito", sa.String(1), nullable=True),
        sa.Column("tem_figura", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confianca", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("aviso", sa.String(200), nullable=False, server_default=""),
        sa.Column("revisada", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("descartada", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_questions_exam_id", "questions", ["exam_id"])
    op.create_table(
        "choices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("letra", sa.String(1), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_choices_question_id", "choices", ["question_id"])


def downgrade() -> None:
    op.drop_table("choices")
    op.drop_index("ix_questions_exam_id", table_name="questions")
    op.drop_table("questions")
    op.drop_table("exams")
