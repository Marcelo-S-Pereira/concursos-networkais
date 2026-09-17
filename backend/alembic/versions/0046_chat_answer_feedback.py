"""[153]: `chat_answers` (resposta real dada no Chat de estudos, hoje só
texto solto em ChatMessage — nunca entrava em Mastery/Dificuldade/Revisão);
`review_schedule.origem` (simulado|chat); `feedback` (estrelas+texto por
ferramenta).

Revision ID: 0046_chat_answer_revisao_origem_feedback
Revises: 0045_voz_escolhida
"""

import sqlalchemy as sa

from alembic import op

revision = "0046_chat_answer_feedback"
down_revision = "0045_voz_escolhida"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "conversation_id", sa.Integer(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("letra", sa.String(1), nullable=False),
        sa.Column("correta", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chat_answers_user_id", "chat_answers", ["user_id"])
    op.create_index("ix_chat_answers_conversation_id", "chat_answers", ["conversation_id"])
    op.create_index("ix_chat_answers_question_id", "chat_answers", ["question_id"])

    op.add_column(
        "review_schedule",
        sa.Column("origem", sa.String(10), nullable=False, server_default="simulado"),
    )

    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ferramenta", sa.String(20), nullable=False),
        sa.Column("estrelas", sa.Integer(), nullable=True),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_feedback_user_id", "feedback", ["user_id"])
    op.create_index("ix_feedback_ferramenta", "feedback", ["ferramenta"])


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_column("review_schedule", "origem")
    op.drop_table("chat_answers")
