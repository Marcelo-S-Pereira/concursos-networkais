"""Classificação por ferramenta ([106]): cada documento RAG diz em quais
ferramentas pode ser usado — Chat de estudos, Tutor IA, Simulado/Caderno de
questões. Nenhuma delas consulta RAG hoje ainda; isto é a fundação (o
booleano + o filtro em `buscar`/`perguntar`), não a integração em si.

Revision ID: 0035_rag_classificacao_uso
Revises: 0034_cpf_indice_nao_unico
"""

import sqlalchemy as sa

from alembic import op

revision = "0035_rag_classificacao_uso"
down_revision = "0034_cpf_indice_nao_unico"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rag_documents", sa.Column("uso_chat", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("rag_documents", sa.Column("uso_tutor", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("rag_documents", sa.Column("uso_simulado", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("rag_documents", "uso_simulado")
    op.drop_column("rag_documents", "uso_tutor")
    op.drop_column("rag_documents", "uso_chat")
