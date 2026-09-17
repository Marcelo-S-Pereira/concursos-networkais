"""Escolha de voz do Kokoro por conversa (Chat de estudo e Tutor IA — mesma
tabela, [109]). `conversations.voz_escolhida` guarda o id da voz Kokoro
(pf_dora/pm_alex/pm_santa, [095]) escolhida pelo aluno; NULL = usa o padrão
(`VOZES_PADRAO`, hoje pf_dora). Aplica tanto ao "Modo voz" (REST, [095]) quanto
ao "Tempo real" (WebSocket, [136]) — os dois chamam `falar_texto`/TTS a partir
da mesma conversa.

Revision ID: 0045_voz_escolhida
Revises: 0044_prompt_modo_voz
"""

import sqlalchemy as sa

from alembic import op

revision = "0045_voz_escolhida"
down_revision = "0044_prompt_modo_voz"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("voz_escolhida", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "voz_escolhida")
