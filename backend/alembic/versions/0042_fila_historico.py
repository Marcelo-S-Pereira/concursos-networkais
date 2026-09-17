"""[126]: fila de admissão para chamadas de IA — histórico persistido
(amostras periódicas de CPU/memória/disco + estado da fila) para o admin
decidir quando escalar o servidor a partir de tendência, não só do
instantâneo. A configuração da fila em si (teto de concorrência, limiares
de recurso, timeout de espera) mora em `system_settings` (flags.py),
sem migration própria — só a tabela de histórico precisa de uma.

Revision ID: 0042_fila_historico
Revises: 0041_prompts
"""

import sqlalchemy as sa

from alembic import op

revision = "0042_fila_historico"
down_revision = "0041_prompts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fila_historico",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cpu_pct", sa.Float(), nullable=True),
        sa.Column("memoria_pct", sa.Float(), nullable=True),
        sa.Column("disco_pct", sa.Float(), nullable=True),
        sa.Column("em_voo", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("esperando", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_concorrente", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("admitidas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejeitadas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("espera_media_ms", sa.Integer(), nullable=True),
    )
    op.create_index("ix_fila_historico_criado_em", "fila_historico", ["criado_em"])


def downgrade() -> None:
    op.drop_index("ix_fila_historico_criado_em", table_name="fila_historico")
    op.drop_table("fila_historico")
