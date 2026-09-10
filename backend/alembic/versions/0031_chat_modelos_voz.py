"""Escolha de IA de voz (TTS) e transcrição (STT) por conversa, + modo de
conversa (texto/voz). A execução ainda não existe (cliente.py só fala
/chat/completions e /embeddings) — isto só deixa a ESCOLHA salva, para quando o
motor de voz for ligado ela já estar lá (mesmo raciocínio do [050]).

Revision ID: 0031_chat_modelos_voz
Revises: 0030_chat_modelos
"""

import sqlalchemy as sa

from alembic import op

revision = "0031_chat_modelos_voz"
down_revision = "0030_chat_modelos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("modelo_voz_id", sa.Integer(), nullable=True))
    op.add_column("conversations", sa.Column("modelo_transcricao_id", sa.Integer(), nullable=True))
    op.add_column("conversations", sa.Column("modo_voz", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("conversations", "modo_voz")
    op.drop_column("conversations", "modelo_transcricao_id")
    op.drop_column("conversations", "modelo_voz_id")
