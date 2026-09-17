"""[132]: nova linha no catálogo de prompts — addendum concatenado ao system
prompt do Chat/Tutor IA sempre que a resposta vai ser falada (TTS), pra o LLM
saber que está numa conversa por voz e parar de dizer "não posso ouvir sons".
Insere só a linha nova (as 12 de 0041_prompts já existem) — filtra a lista de
seed pela chave nova em vez de duplicar o texto aqui.

Revision ID: 0044_prompt_modo_voz
Revises: 0043_component_icons
"""

import sqlalchemy as sa
from sqlalchemy import Text, column, table

from alembic import op
from app.modules.prompts.seed import PROMPTS

revision = "0044_prompt_modo_voz"
down_revision = "0043_component_icons"
branch_labels = None
depends_on = None

_CHAVE = "chat_modo_voz_addendum"


def upgrade() -> None:
    linha = next(p for p in PROMPTS if p["chave"] == _CHAVE)
    tabela = table(
        "prompts",
        column("chave", Text), column("nome", Text), column("onde_usado", Text),
        column("como_funciona", Text), column("texto", Text),
    )
    op.bulk_insert(tabela, [linha])


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM prompts WHERE chave = :chave").bindparams(chave=_CHAVE))
