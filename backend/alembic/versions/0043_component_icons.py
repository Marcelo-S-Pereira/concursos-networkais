"""[128]: aba Ícones — o admin escolhe (biblioteca curada ou upload) o ícone
de cada botão/aba do app, em vez de aceitar os que o assistente de IA escolheu.
`component_icons` guarda só a ESCOLHA feita por slot; sem linha = usa o
texto padrão (comportamento de hoje). O catálogo fixo dos slots que existem
vive em código (`app/modules/icones/catalogo.py`), não precisa de migration
pra crescer.

Revision ID: 0043_component_icons
Revises: 0042_fila_historico
"""

import sqlalchemy as sa

from alembic import op

revision = "0043_component_icons"
down_revision = "0042_fila_historico"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "component_icons",
        sa.Column("slot", sa.Text(), primary_key=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("valor", sa.Text(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("component_icons")
