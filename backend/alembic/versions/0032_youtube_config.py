"""Chave da YouTube Data API v3 (busca real de vídeos no chat).

Revision ID: 0032_youtube_config
Revises: 0031_chat_modelos_voz
"""

import sqlalchemy as sa

from alembic import op

revision = "0032_youtube_config"
down_revision = "0031_chat_modelos_voz"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "youtube_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chave_cifrada", sa.String(length=1000), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("youtube_config")
