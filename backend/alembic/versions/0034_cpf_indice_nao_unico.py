"""CPF deixa de ser único no banco — a unicidade normal agora é aplicada em
código ([102]), com uma exceção: o CPF do próprio superadmin pode se repetir
em várias contas, para ele testar. O índice continua existindo (a busca por
CPF ainda usa `cpf_indice`), só perde a restrição UNIQUE.

Revision ID: 0034_cpf_indice_nao_unico
Revises: 0033_feature_grants
"""

from alembic import op

revision = "0034_cpf_indice_nao_unico"
down_revision = "0033_feature_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_users_cpf_indice", table_name="users")
    op.create_index("ix_users_cpf_indice", "users", ["cpf_indice"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_cpf_indice", table_name="users")
    op.create_index("ix_users_cpf_indice", "users", ["cpf_indice"], unique=True)
