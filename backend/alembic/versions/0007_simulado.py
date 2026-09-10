"""Simulado por tempo: simulation_runs e simulation_answers.

Revision ID: 0007_simulado
Revises: 0006_questao_pagina
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_simulado"
down_revision = "0006_questao_pagina"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exam_id", sa.Integer(), sa.ForeignKey("exams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("acertos", sa.Integer(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_simulation_runs_exam_id", "simulation_runs", ["exam_id"])
    op.create_index("ix_simulation_runs_user_id", "simulation_runs", ["user_id"])
    op.create_table(
        "simulation_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("letra", sa.String(1), nullable=True),
        sa.Column("correta", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tempo_resposta_s", sa.Integer(), nullable=True),
        sa.Column("alteracoes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_simulation_answers_run_id", "simulation_answers", ["run_id"])


def downgrade() -> None:
    op.drop_table("simulation_answers")
    op.drop_table("simulation_runs")
