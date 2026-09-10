"""Total de inscritos por caderno (para estimar o ranking).

Revision ID: 0018_total_inscritos
Revises: 0017_rag
"""

import sqlalchemy as sa

from alembic import op

revision = "0018_total_inscritos"
down_revision = "0017_rag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exam_rules", sa.Column("total_inscritos", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("exam_rules", "total_inscritos")
