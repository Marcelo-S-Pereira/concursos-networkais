"""Plataforma como registro mestre; modelos viram filhos.

Endpoint e chave saem de `ai_connections` e passam a morar em `ai_platforms`,
uma linha por provedor. As conexões existentes viram modelos ligados a uma
plataforma criada a partir dos próprios dados delas — nada é apagado, e a chave
cifrada é transferida, não regerada (a cifra é a mesma).

DDL no Postgres é transacional: ou a migration inteira passa, ou nada muda.

Revision ID: 0012_ai_platforms
Revises: 0011_enunciado_col2
"""

import sqlalchemy as sa

from alembic import op

revision = "0012_ai_platforms"
down_revision = "0011_enunciado_col2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_platforms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("titulo", sa.String(length=120), nullable=False),
        sa.Column("endpoint", sa.String(length=500), nullable=False),
        sa.Column("api_key_cifrada", sa.String(length=1000), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column("ai_connections", sa.Column("platform_id", sa.Integer(), nullable=True))

    # Uma plataforma por (endpoint, chave) já existente. O título sai do host do
    # endpoint — "api.together.xyz" vira "Together"; o usuário renomeia depois.
    op.execute("""
        INSERT INTO ai_platforms (titulo, endpoint, api_key_cifrada)
        SELECT DISTINCT ON (endpoint, api_key_cifrada)
               initcap(split_part(replace(replace(endpoint, 'https://', ''), 'http://', ''), '.', 2)),
               endpoint, api_key_cifrada
        FROM ai_connections
    """)
    op.execute("""
        UPDATE ai_connections c
           SET platform_id = p.id
        FROM ai_platforms p
        WHERE p.endpoint = c.endpoint AND p.api_key_cifrada = c.api_key_cifrada
    """)

    # Só agora, com todas as linhas ligadas, o vínculo vira obrigatório.
    op.alter_column("ai_connections", "platform_id", nullable=False)
    op.create_index("ix_ai_connections_platform_id", "ai_connections", ["platform_id"])
    op.create_foreign_key(
        "fk_ai_connections_platform", "ai_connections", "ai_platforms",
        ["platform_id"], ["id"], ondelete="CASCADE",
    )

    op.drop_column("ai_connections", "endpoint")
    op.drop_column("ai_connections", "api_key_cifrada")


def downgrade() -> None:
    op.add_column("ai_connections", sa.Column("endpoint", sa.String(length=500), nullable=True))
    op.add_column("ai_connections", sa.Column("api_key_cifrada", sa.String(length=1000), nullable=True))
    op.execute("""
        UPDATE ai_connections c
           SET endpoint = p.endpoint, api_key_cifrada = p.api_key_cifrada
        FROM ai_platforms p
        WHERE p.id = c.platform_id
    """)
    op.alter_column("ai_connections", "endpoint", nullable=False)
    op.alter_column("ai_connections", "api_key_cifrada", nullable=False)
    op.drop_constraint("fk_ai_connections_platform", "ai_connections", type_="foreignkey")
    op.drop_index("ix_ai_connections_platform_id", table_name="ai_connections")
    op.drop_column("ai_connections", "platform_id")
    op.drop_table("ai_platforms")
