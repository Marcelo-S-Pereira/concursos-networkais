"""Habilita a extensão pgvector.

Primeira migration do projeto. A extensão vem embutida na imagem
pgvector/pgvector:pg16 (nunca instalada dentro do container em execução - ver
registro interno, registro [005]); aqui só a habilitamos no banco.

Revision ID: 0001_extensao_vector
Revises:
"""

from alembic import op

revision = "0001_extensao_vector"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Não derrubamos a extensão: qualquer coluna vector existente iria junto.
    pass
