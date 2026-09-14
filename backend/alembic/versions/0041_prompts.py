"""[125]: catálogo de prompts — a base de dados vira a ÚNICA fonte de verdade
do texto enviado à IA e da descrição de cada prompt (nome/onde é usado/como
funciona). Cria a tabela `prompts` e semeia as 12 linhas com o texto EXATO
que hoje está hardcoded em 7 módulos Python — a lista de seed mora em
`app.modules.prompts.seed` (fonte única, reusada também por
`tests/conftest.py` para semear o banco de teste, já que `create_all` só cria
o schema, não os dados). Depois desta migration, os módulos passam a chamar
`prompts.buscar(db, chave)` em vez de usar a string fixa.

Revision ID: 0041_prompts
Revises: 0040_login_senha
"""

import sqlalchemy as sa
from sqlalchemy import Text, column, table

from alembic import op
from app.modules.prompts.seed import PROMPTS

revision = "0041_prompts"
down_revision = "0040_login_senha"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompts",
        sa.Column("chave", sa.Text(), primary_key=True),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("onde_usado", sa.Text(), nullable=False),
        sa.Column("como_funciona", sa.Text(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    tabela = table(
        "prompts",
        column("chave", Text), column("nome", Text), column("onde_usado", Text),
        column("como_funciona", Text), column("texto", Text),
    )
    op.bulk_insert(tabela, PROMPTS)


def downgrade() -> None:
    op.drop_table("prompts")
