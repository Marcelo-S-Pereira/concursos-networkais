"""[171]: indexador do RAG em segundo plano (serviço `concursos-indexador`).

Vetoriza, com o modelo da conexão de embeddings ativa, todo trecho que ainda não
tem vetor DESSE modelo. Isso cobre documento novo, troca de modelo e retomada
depois de queda, sem estado extra: "pendente" é sempre derivado do banco.

- documentos com menos trechos pendentes vão primeiro (um PDF pequeno não espera
  a reindexação de uma apostila inteira);
- texto idêntico a um trecho já vetorizado reaproveita o vetor;
- roda com prioridade baixa e 1 thread, e se recolhe quando o servidor está
  ocupado — o portão de admissão do [126] barra as chamadas de IA acima de 78%
  de carga por núcleo, e a indexação não pode ser o motivo disso.
"""

import logging
import os
import time
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import RagChunk, RagDocument
from app.db.session import SessionLocal
from app.modules.ai_registry.cliente import AiCallError
from app.modules.ai_registry.servico import SemConexaoIA, gerar_embeddings, modelo_de_embeddings

log = logging.getLogger("concursos.indexador")

LOTE = 8
CARGA_MAXIMA_POR_NUCLEO = 0.75
ESPERA_OCIOSO_S = 30
ESPERA_CARGA_S = 20
ESPERA_ERRO_S = 60


def _pendente(modelo: str):
    return or_(RagChunk.embedding.is_(None), RagChunk.embedding_modelo.is_distinct_from(modelo))


def progresso(db: Session, modelo: str | None) -> dict[int, int]:
    """Quantos trechos de cada documento já têm vetor do modelo atual."""
    if not modelo:
        return {}
    linhas = db.execute(
        select(RagChunk.document_id, func.count())
        .where(RagChunk.embedding.is_not(None), RagChunk.embedding_modelo == modelo)
        .group_by(RagChunk.document_id)
    ).all()
    return {doc_id: n for doc_id, n in linhas}


def processar_um_lote(db: Session, modelo: str, tentou: set[int]) -> int:
    """Vetoriza até `LOTE` trechos do documento mais curto da fila. Devolve quantos
    trechos foram gravados (0 = nada pendente)."""
    pend = _pendente(modelo)
    alvo = db.execute(
        select(RagChunk.document_id).where(pend).group_by(RagChunk.document_id)
        .order_by(func.count(), RagChunk.document_id).limit(1)
    ).scalar()
    if alvo is None:
        return 0
    doc = db.get(RagDocument, alvo)
    if doc.id not in tentou:
        tentou.add(doc.id)
        doc.tentativas_indexacao += 1
        db.commit()

    chunks = db.execute(
        select(RagChunk).where(RagChunk.document_id == alvo, pend).order_by(RagChunk.id).limit(LOTE)
    ).scalars().all()
    unicos = list(dict.fromkeys(c.conteudo for c in chunks))
    prontos = dict(db.execute(
        select(RagChunk.conteudo, RagChunk.embedding)
        .where(RagChunk.embedding.is_not(None), RagChunk.embedding_modelo == modelo, RagChunk.conteudo.in_(unicos))
        .distinct(RagChunk.conteudo)
    ).all())
    faltam = [t for t in unicos if t not in prontos]
    modelo_usado = modelo
    if faltam:
        try:
            vetores, modelo_usado = gerar_embeddings(
                db, faltam, origem="rag_ingest", tipo="passagem", somente_primeira=True,
            )
        except (SemConexaoIA, AiCallError) as e:
            doc.erro = str(e)[:500]
            db.commit()
            raise
        prontos.update(zip(faltam, vetores, strict=True))
    for c in chunks:
        c.embedding = prontos[c.conteudo]
        c.embedding_modelo = modelo_usado

    db.flush()
    restam = db.scalar(select(func.count()).select_from(RagChunk).where(RagChunk.document_id == alvo, pend))
    if not restam:
        doc.indexado_em = datetime.now(UTC)
        doc.erro = None
        log.info("documento %s (%s) indexado por completo", doc.id, doc.titulo[:60])
    db.commit()
    return len(chunks)


def _carga_por_nucleo() -> float:
    return os.getloadavg()[0] / (os.cpu_count() or 1)


def rodar() -> None:
    tentou: set[int] = set()
    log.info("indexador iniciado (pid %s, %s nucleos)", os.getpid(), os.cpu_count())
    while True:
        espera = 0
        try:
            with SessionLocal() as db:
                modelo = modelo_de_embeddings(db)
                if not modelo:
                    espera = ESPERA_ERRO_S
                elif _carga_por_nucleo() > CARGA_MAXIMA_POR_NUCLEO:
                    espera = ESPERA_CARGA_S
                elif processar_um_lote(db, modelo, tentou) == 0:
                    espera = ESPERA_OCIOSO_S
        except (SemConexaoIA, AiCallError) as e:
            log.warning("indexação pausada: %s", str(e)[:200])
            espera = ESPERA_ERRO_S
        except Exception:  # noqa: BLE001 — o serviço não pode morrer por um lote ruim
            log.exception("erro inesperado no indexador")
            espera = ESPERA_ERRO_S
        if espera:
            time.sleep(espera)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    rodar()
