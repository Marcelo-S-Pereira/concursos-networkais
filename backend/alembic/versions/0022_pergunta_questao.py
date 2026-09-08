"""Campo pergunta (o enunciado da questão), separado do texto de apoio (2 colunas).

Revision ID: 0022_pergunta_questao
Revises: 0021_lixeira_cadernos
"""

import sqlalchemy as sa

from alembic import op

revision = "0022_pergunta_questao"
down_revision = "0021_lixeira_cadernos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("pergunta", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("questions", "pergunta")
