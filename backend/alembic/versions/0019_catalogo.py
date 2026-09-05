"""Catálogo de plataformas e modelos (LLM/VLM/embeddings/STT/TTS) na base.

Revision ID: 0019_catalogo
Revises: 0018_total_inscritos
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_catalogo"
down_revision = "0018_total_inscritos"
branch_labels = None
depends_on = None

PLATAFORMAS = [
    ("Together", "https://api.together.xyz/v1"),
    ("OpenAI", "https://api.openai.com/v1"),
    ("OpenRouter", "https://openrouter.ai/api/v1"),
    ("Grok (xAI)", "https://api.x.ai/v1"),
    ("Hugging Face", "https://router.huggingface.co/v1"),
]

# (plataforma, categoria, model_id, rotulo, dim, padrao) — semente inicial;
# editável pela tela e sincronizável do provedor (GET /models).
MODELOS = [
    ("Together", "texto", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "validado pelo usuário", None, True),
    ("Together", "texto", "Qwen/Qwen2.5-72B-Instruct-Turbo", "", None, False),
    ("Together", "texto", "deepseek-ai/DeepSeek-V3", "", None, False),
    ("Together", "visao", "meta-llama/Llama-3.2-90B-Vision-Instruct-Turbo", "", None, True),
    ("Together", "visao", "Qwen/Qwen2-VL-72B-Instruct", "", None, False),
    ("Together", "embeddings", "intfloat/multilingual-e5-large-instruct", "PT-BR, casa com o RAG", 1024, True),
    ("Together", "embeddings", "BAAI/bge-large-en-v1.5", "", 1024, False),
    ("Together", "transcricao", "openai/whisper-large-v3", "", None, True),
    ("Together", "voz", "cartesia/sonic", "", None, True),
    ("OpenAI", "texto", "gpt-4o-mini", "", None, True),
    ("OpenAI", "texto", "gpt-4o", "", None, False),
    ("OpenAI", "visao", "gpt-4o", "", None, True),
    ("OpenAI", "embeddings", "text-embedding-3-small", "dim 1536", 1536, True),
    ("OpenAI", "transcricao", "whisper-1", "", None, True),
    ("OpenAI", "voz", "gpt-4o-mini-tts", "", None, True),
]


def upgrade() -> None:
    plat = op.create_table(
        "ai_catalog_platform",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(80), nullable=False, unique=True),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    modelo = op.create_table(
        "ai_catalog_model",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plataforma", sa.String(80), nullable=False),
        sa.Column("categoria", sa.String(20), nullable=False),
        sa.Column("model_id", sa.String(200), nullable=False),
        sa.Column("rotulo", sa.String(200), nullable=False, server_default=""),
        sa.Column("dim", sa.Integer(), nullable=True),
        sa.Column("padrao", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("plataforma", "categoria", "model_id", name="uq_catalog_model"),
    )
    op.create_index("ix_ai_catalog_model_plataforma", "ai_catalog_model", ["plataforma"])
    op.create_index("ix_ai_catalog_model_categoria", "ai_catalog_model", ["categoria"])

    op.bulk_insert(plat, [{"nome": n, "endpoint": e} for n, e in PLATAFORMAS])
    op.bulk_insert(modelo, [
        {"plataforma": p, "categoria": c, "model_id": m, "rotulo": r, "dim": d, "padrao": pd}
        for p, c, m, r, d, pd in MODELOS
    ])


def downgrade() -> None:
    op.drop_table("ai_catalog_model")
    op.drop_table("ai_catalog_platform")
