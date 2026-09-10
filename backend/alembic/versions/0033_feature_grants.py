"""Liberação de recursos restritos por usuário, com cota diária + uso real.

`feature_grants`: quem pode usar qual recurso restrito e quantas vezes por dia.
`resource_usage_log`: uma linha por uso real (mesmo molde do ai_call_log), base
para contar "quanto já usou hoje" — sem isso não dá para aplicar a cota.

Revision ID: 0033_feature_grants
Revises: 0032_youtube_config
"""

import sqlalchemy as sa

from alembic import op

revision = "0033_feature_grants"
down_revision = "0032_youtube_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature", sa.String(length=40), nullable=False),
        sa.Column("limite_diario", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("concedido_por", sa.Integer(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_feature_grants_user_id", "feature_grants", ["user_id"])
    op.create_unique_constraint("uq_feature_grants_user_feature", "feature_grants", ["user_id", "feature"])

    op.create_table(
        "resource_usage_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature", sa.String(length=40), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_resource_usage_log_user_id", "resource_usage_log", ["user_id"])
    op.create_index("ix_resource_usage_log_feature", "resource_usage_log", ["feature"])
    op.create_index("ix_resource_usage_log_criado_em", "resource_usage_log", ["criado_em"])


def downgrade() -> None:
    op.drop_index("ix_resource_usage_log_criado_em", table_name="resource_usage_log")
    op.drop_index("ix_resource_usage_log_feature", table_name="resource_usage_log")
    op.drop_index("ix_resource_usage_log_user_id", table_name="resource_usage_log")
    op.drop_table("resource_usage_log")

    op.drop_constraint("uq_feature_grants_user_feature", "feature_grants", type_="unique")
    op.drop_index("ix_feature_grants_user_id", table_name="feature_grants")
    op.drop_table("feature_grants")
