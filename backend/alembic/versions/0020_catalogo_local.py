"""Plataforma e modelos LOCAIS (rodam na ambiente de execucao): Kokoro/whisper/embeddings.

Revision ID: 0020_catalogo_local
Revises: 0019_catalogo
"""

from sqlalchemy import Boolean, Integer, String, column, table

from alembic import op

revision = "0020_catalogo_local"
down_revision = "0019_catalogo"
branch_labels = None
depends_on = None

LOCAL_ENDPOINT = "local://runtime"

MODELOS = [
    # (categoria, model_id, rotulo, dim, padrao)
    ("voz", "hexgrad/Kokoro-82M", "TTS local, leve (recomendado)", None, True),
    ("voz", "rhasspy/piper", "TTS local, muito leve", None, False),
    ("voz", "coqui/XTTS-v2", "TTS local, vozes clonáveis (mais pesado)", None, False),
    ("transcricao", "faster-whisper-large-v3", "STT local, melhor qualidade", None, True),
    ("transcricao", "faster-whisper-medium", "STT local, equilíbrio", None, False),
    ("transcricao", "faster-whisper-small", "STT local, mais rápido/quantizado", None, False),
    ("transcricao", "vosk-model-pt", "STT local, offline muito leve", None, False),
    ("embeddings", "intfloat/multilingual-e5-large-instruct", "embeddings local (sentence-transformers), casa com o RAG", 1024, True),
    ("texto", "llama3.2:3b", "LLM local via Ollama (leve)", None, False),
    ("texto", "qwen2.5:7b", "LLM local via Ollama", None, False),
]


def upgrade() -> None:
    plat = table("ai_catalog_platform", column("nome", String), column("endpoint", String))
    op.bulk_insert(plat, [{"nome": "Local (ambiente de execucao)", "endpoint": LOCAL_ENDPOINT}])
    modelo = table(
        "ai_catalog_model",
        column("plataforma", String), column("categoria", String), column("model_id", String),
        column("rotulo", String), column("dim", Integer), column("padrao", Boolean),
    )
    op.bulk_insert(modelo, [
        {"plataforma": "Local (ambiente de execucao)", "categoria": c, "model_id": m, "rotulo": r, "dim": d, "padrao": pd}
        for c, m, r, d, pd in MODELOS
    ])


def downgrade() -> None:
    op.execute("DELETE FROM ai_catalog_model WHERE plataforma = 'Local (ambiente de execucao)'")
    op.execute("DELETE FROM ai_catalog_platform WHERE nome = 'Local (ambiente de execucao)'")
