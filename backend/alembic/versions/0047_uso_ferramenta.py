"""[170]: `ai_call_log` passa a registrar POR QUAL FERRAMENTA e em QUAL AÇÃO do
usuário cada chamada de IA aconteceu — a base para medir custo por usuário e por
ferramenta e definir limites justos com dado real, em vez de palpite.

- `ferramenta`: chat_estudo | tutor_ia | tutor_ia_tempo_real | simulado_tutor |
  gemeas | passo_a_passo | admin. Histórico antigo fica NULL (não invento).
- `conversation_id`: a conversa (Chat de estudo / Tutor IA), quando houver.
- `acao_id`: agrupa as chamadas de UMA ação do usuário (uma mensagem de voz =
  transcrição + busca na biblioteca + LLM + voz). É a unidade justa de limite.

Revision ID: 0047_uso_ferramenta
Revises: 0046_chat_answer_feedback
"""

import sqlalchemy as sa

from alembic import op

revision = "0047_uso_ferramenta"
down_revision = "0046_chat_answer_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_call_log", sa.Column("ferramenta", sa.String(30), nullable=True))
    op.add_column("ai_call_log", sa.Column("conversation_id", sa.Integer(), nullable=True))
    op.add_column("ai_call_log", sa.Column("acao_id", sa.String(32), nullable=True))
    op.create_index("ix_ai_call_log_ferramenta", "ai_call_log", ["ferramenta"])
    op.create_index("ix_ai_call_log_conversation_id", "ai_call_log", ["conversation_id"])
    op.create_index("ix_ai_call_log_acao_id", "ai_call_log", ["acao_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_call_log_acao_id", table_name="ai_call_log")
    op.drop_index("ix_ai_call_log_conversation_id", table_name="ai_call_log")
    op.drop_index("ix_ai_call_log_ferramenta", table_name="ai_call_log")
    op.drop_column("ai_call_log", "acao_id")
    op.drop_column("ai_call_log", "conversation_id")
    op.drop_column("ai_call_log", "ferramenta")
