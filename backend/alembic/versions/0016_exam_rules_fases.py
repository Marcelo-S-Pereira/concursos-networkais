"""Regras por fase no edital: fases, mínimo % por fase, matérias sem zero.

Revision ID: 0016_exam_rules_fases
Revises: 0015_twin_questions
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016_exam_rules_fases"
down_revision = "0015_twin_questions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exam_rules", sa.Column("fases", JSONB(), nullable=False, server_default="{}"))
    op.add_column("exam_rules", sa.Column("minimo_pct_fase", JSONB(), nullable=False, server_default="{}"))
    op.add_column("exam_rules", sa.Column("materias_sem_zero", JSONB(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("exam_rules", "materias_sem_zero")
    op.drop_column("exam_rules", "minimo_pct_fase")
    op.drop_column("exam_rules", "fases")
