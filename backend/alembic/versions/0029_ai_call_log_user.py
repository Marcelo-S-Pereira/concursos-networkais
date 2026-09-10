"""user_id no ai_call_log: base dos limites rolantes por usuário.

Nullable de propósito — as chamadas antigas não têm dono conhecido, e inventar
um seria mentir sobre o histórico.

Revision ID: 0029_ai_call_log_user
Revises: 0028_chat
"""

import sqlalchemy as sa

from alembic import op

revision = "0029_ai_call_log_user"
down_revision = "0028_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_call_log", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_index("ix_ai_call_log_user_id", "ai_call_log", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_call_log_user_id", table_name="ai_call_log")
    op.drop_column("ai_call_log", "user_id")
