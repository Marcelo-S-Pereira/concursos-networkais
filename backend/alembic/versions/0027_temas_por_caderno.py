"""Subtemas por caderno + estatística por subtema (exam_id/disciplina).

Revision ID: 0027_temas_por_caderno
Revises: 0026_usuario_vitalicio
"""

import sqlalchemy as sa

from alembic import op

revision = "0027_temas_por_caderno"
down_revision = "0026_usuario_vitalicio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "temas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exam_id", sa.Integer(), sa.ForeignKey("exams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("disciplina", sa.String(length=120), nullable=False),
        sa.Column("nome", sa.String(length=200), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_temas_exam_id", "temas", ["exam_id"])
    op.create_index("ix_temas_disciplina", "temas", ["disciplina"])

    op.add_column("emphasis_public_stats", sa.Column("exam_id", sa.Integer(), nullable=True))
    op.add_column("emphasis_public_stats", sa.Column("disciplina", sa.String(length=120), nullable=False, server_default=""))
    op.create_index("ix_emphasis_public_stats_exam_id", "emphasis_public_stats", ["exam_id"])
    op.alter_column("emphasis_public_stats", "enfase", type_=sa.String(length=200))


def downgrade() -> None:
    op.drop_index("ix_emphasis_public_stats_exam_id", table_name="emphasis_public_stats")
    op.drop_column("emphasis_public_stats", "disciplina")
    op.drop_column("emphasis_public_stats", "exam_id")
    op.drop_index("ix_temas_disciplina", table_name="temas")
    op.drop_index("ix_temas_exam_id", table_name="temas")
    op.drop_table("temas")
