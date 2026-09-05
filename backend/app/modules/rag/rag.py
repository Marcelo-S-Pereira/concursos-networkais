"""Biblioteca RAG em PostgreSQL/pgvector.

Chunk de 900 chars com 100 de sobreposição (corta por parágrafo). 1 embedding
por chunk, em lote. Busca por distância de cosseno. Tolerante: se não houver
conexão de embeddings, o texto do chunk é salvo sem vetor e é reindexado depois.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import RagChunk, RagDocument
from app.modules.ai_registry.servico import SemConexaoIA, gerar_embeddings

log = logging.getLogger("concursos.rag")

CHUNK = 900
OVERLAP = 100
LOTE = 64


def dividir(texto: str) -> list[str]:
    paras = [p.strip() for p in texto.split("\n\n") if p.strip()]
    chunks: list[str] = []
    atual = ""
    for p in paras:
        if len(p) > CHUNK:
            if atual:
                chunks.append(atual)
                atual = ""
            passo = CHUNK - OVERLAP
            for i in range(0, len(p), passo):
                chunks.append(p[i : i + CHUNK])
            continue
        if len(atual) + len(p) + 2 > CHUNK:
            chunks.append(atual)
            atual = ""
        atual = f"{atual}\n\n{p}" if atual else p
    if atual:
        chunks.append(atual)
    return chunks


def _embed_pendentes(db: Session, doc: RagDocument) -> None:
    """Gera embeddings para os chunks sem vetor deste documento, em lote."""
    pendentes = db.execute(
        select(RagChunk).where(RagChunk.document_id == doc.id, RagChunk.embedding.is_(None))
    ).scalars().all()
    if not pendentes:
        return
    for i in range(0, len(pendentes), LOTE):
        bloco = pendentes[i : i + LOTE]
        vetores = gerar_embeddings(db, [f"passage: {c.conteudo}" for c in bloco], origem="rag_ingest")
        for chunk, vetor in zip(bloco, vetores, strict=True):
            chunk.embedding = vetor
    db.commit()


def ingerir_documento(db: Session, titulo: str, texto: str, colecao: str = "oficial", origem: str = "") -> RagDocument:
    doc = RagDocument(titulo=titulo, colecao=colecao, origem=origem)
    db.add(doc)
    db.flush()
    pedacos = dividir(texto)
    for i, c in enumerate(pedacos):
        db.add(RagChunk(document_id=doc.id, colecao=colecao, chunk_index=i, conteudo=c))
    doc.chunk_count = len(pedacos)
    db.commit()

    # tenta indexar já; se não houver conexão de embeddings, fica pendente
    try:
        _embed_pendentes(db, doc)
        doc.indexado_em = datetime.now(UTC)
        doc.erro = None
    except SemConexaoIA:
        doc.erro = "sem conexão de embeddings — chunks salvos, reindexar depois"
    except Exception as e:  # noqa: BLE001
        doc.erro = str(e)[:500]
    db.commit()
    db.refresh(doc)
    return doc


def buscar(db: Session, consulta: str, colecao: str | None = None, k: int = 6) -> list[dict]:
    """Busca por similaridade de cosseno. Só entre chunks já vetorizados."""
    vetor = gerar_embeddings(db, [f"Instruct: buscar trecho relevante\nQuery: {consulta}"], origem="rag_busca")[0]
    literal = "[" + ",".join(str(x) for x in vetor) + "]"
    sql = """
        SELECT c.conteudo, d.titulo, c.chunk_index
        FROM rag_chunks c JOIN rag_documents d ON d.id = c.document_id
        WHERE c.embedding IS NOT NULL
    """
    params = {"vec": literal, "k": k}
    if colecao:
        sql += " AND c.colecao = :colecao"
        params["colecao"] = colecao
    sql += " ORDER BY c.embedding <=> CAST(:vec AS vector) LIMIT :k"
    linhas = db.execute(text(sql), params).all()
    return [{"titulo": t, "chunk": idx, "conteudo": cont} for cont, t, idx in linhas]
