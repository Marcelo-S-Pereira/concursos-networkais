"""Motor de conexão de IA: ai_connections e ai_call_log.

Revision ID: 0004_ai_registry
Revises: 0003_cadastro_e_login_por_codigo
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_ai_registry"
down_revision = "0003_cadastro_e_login_por_codigo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("api_key_cifrada", sa.String(1000), nullable=False),
        sa.Column("modelo", sa.String(200), nullable=False),
        sa.Column("categoria", sa.String(20), nullable=False, server_default="texto"),
        sa.Column("tipo_deploy", sa.String(20), nullable=False, server_default="serverless"),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ordem_fallback", sa.Integer(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="4000"),
        sa.Column("temperatura", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("context_window_tokens", sa.Integer(), nullable=True),
        sa.Column("rate_limit_rpm", sa.Integer(), nullable=True),
        sa.Column("preco_entrada_por_milhao", sa.Float(), nullable=True),
        sa.Column("preco_saida_por_milhao", sa.Float(), nullable=True),
        sa.Column("moeda", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_connections_categoria", "ai_connections", ["categoria"])

    op.create_table(
        "ai_call_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), nullable=True),
        sa.Column("categoria", sa.String(20), nullable=False),
        sa.Column("origem", sa.String(60), nullable=False),
        sa.Column("modelo", sa.String(200), nullable=False),
        sa.Column("sucesso", sa.Boolean(), nullable=False),
        sa.Column("latencia_ms", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("unidades", sa.Integer(), nullable=True),
        sa.Column("tipo_unidade", sa.String(16), nullable=True),
        sa.Column("erro", sa.String(500), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_call_log_connection_id", "ai_call_log", ["connection_id"])
    op.create_index("ix_ai_call_log_criado_em", "ai_call_log", ["criado_em"])


def downgrade() -> None:
    op.drop_table("ai_call_log")
    op.drop_index("ix_ai_connections_categoria", table_name="ai_connections")
    op.drop_table("ai_connections")
