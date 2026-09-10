"""Cadastro completo e login por código no e-mail (remove a senha).

A tabela `users` de [012] é recriada: tinha senha e não tinha nome, CPF nem
telefone, e não havia dado de produção para preservar (só o usuário de teste).

Revision ID: 0003_cadastro_e_login_por_codigo
Revises: 0002_usuarios
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_cadastro_e_login_por_codigo"
down_revision = "0002_usuarios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(160), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("cpf_cifrado", sa.String(255), nullable=False),
        sa.Column("cpf_indice", sa.String(64), nullable=False),
        sa.Column("telefone", sa.String(20), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="aluno"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_cpf_indice", "users", ["cpf_indice"], unique=True)

    op.create_table(
        "login_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("codigo_hash", sa.String(64), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_login_codes_user_id", "login_codes", ["user_id"])


def downgrade() -> None:
    op.drop_table("login_codes")
    op.drop_index("ix_users_cpf_indice", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
