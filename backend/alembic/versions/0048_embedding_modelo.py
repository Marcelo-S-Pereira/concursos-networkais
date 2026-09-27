"""[171] carimbo do modelo nos vetores do RAG + bge-m3 local no catálogo

Revision ID: 0048_embedding_modelo
Revises: 0047_uso_ferramenta
"""

import sqlalchemy as sa

from alembic import op

revision = "0048_embedding_modelo"
down_revision = "0047_uso_ferramenta"
branch_labels = None
depends_on = None

MODELO_ANTIGO = "intfloat/multilingual-e5-large-instruct"
MODELO_LOCAL = "Xenova/bge-m3"


def upgrade() -> None:
    op.add_column("rag_chunks", sa.Column("embedding_modelo", sa.String(120), nullable=True))
    # os vetores que já existem vieram do e5-instruct: carimbados, deixam de ser
    # confundidos com os do modelo novo e serão refeitos pelo indexador
    op.execute(
        sa.text("UPDATE rag_chunks SET embedding_modelo = :m WHERE embedding IS NOT NULL").bindparams(m=MODELO_ANTIGO)
    )
    op.execute(sa.text(
        "UPDATE ai_catalog_model SET padrao = false "
        "WHERE plataforma = 'Local (ambiente de execucao)' AND categoria = 'embeddings'"
    ))
    op.execute(sa.text(
        "INSERT INTO ai_catalog_model (plataforma, categoria, model_id, rotulo, dim, padrao) "
        "VALUES ('Local (ambiente de execucao)', 'embeddings', :m, 'bge-m3 local (ONNX int8, roda na ambiente de execucao, sem API)', 1024, true)"
    ).bindparams(m=MODELO_LOCAL))


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM ai_catalog_model WHERE plataforma = 'Local (ambiente de execucao)' AND model_id = :m")
        .bindparams(m=MODELO_LOCAL)
    )
    op.drop_column("rag_chunks", "embedding_modelo")
