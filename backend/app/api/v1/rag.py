"""Biblioteca RAG (admin). Importa documentos, indexa (embeddings) e busca por
similaridade. Sem conexão de embeddings, os chunks ficam salvos e são
reindexados quando a conexão existir."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import apenas_superadmin
from app.db.models import RagDocument, User
from app.db.session import get_db

router = APIRouter(prefix="/rag")


class DocOut(BaseModel):
    id: int
    titulo: str
    colecao: str
    chunk_count: int
    indexado: bool
    erro: str | None


def _saida(d: RagDocument) -> DocOut:
    return DocOut(id=d.id, titulo=d.titulo, colecao=d.colecao, chunk_count=d.chunk_count,
                  indexado=d.indexado_em is not None, erro=d.erro)


@router.get("/documentos", response_model=list[DocOut])
def listar(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    return [_saida(d) for d in db.execute(select(RagDocument).order_by(RagDocument.id)).scalars()]


@router.post("/documentos/importar", response_model=DocOut, status_code=201)
async def importar(
    arquivo: UploadFile,
    titulo: str = Form(""),
    colecao: str = Form("oficial"),
    _: User = Depends(apenas_superadmin),
    db: Session = Depends(get_db),
):
    from pypdf import PdfReader

    from app.modules.rag.rag import ingerir_documento

    if arquivo.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="Envie um PDF.")
    dados = await arquivo.read()
    if len(dados) > 32_000_000:
        raise HTTPException(status_code=413, detail="PDF grande demais (máx 32MB).")
    import io

    reader = PdfReader(io.BytesIO(dados))
    texto = "\n\n".join((p.extract_text() or "") for p in reader.pages)
    if not texto.strip():
        raise HTTPException(status_code=422, detail="PDF sem texto extraível (imagem escaneada?).")
    doc = ingerir_documento(db, titulo or arquivo.filename or "Documento", texto, colecao=colecao)
    return _saida(doc)


@router.post("/documentos/{doc_id}/reindexar", response_model=DocOut)
def reindexar(doc_id: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    from app.modules.ai_registry.cliente import AiCallError
    from app.modules.ai_registry.servico import SemConexaoIA
    from app.modules.rag.rag import _embed_pendentes

    doc = db.get(RagDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    try:
        _embed_pendentes(db, doc)
        doc.indexado_em = datetime.now(UTC)
        doc.erro = None
        db.commit()
    except SemConexaoIA as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AiCallError as e:
        raise HTTPException(status_code=502, detail=f"Embeddings falharam: {e}") from e
    return _saida(doc)


@router.delete("/documentos/{doc_id}", status_code=204)
def apagar(doc_id: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    doc = db.get(RagDocument, doc_id)
    if doc:
        db.delete(doc)
        db.commit()


class BuscaIn(BaseModel):
    consulta: str
    colecao: str | None = None


@router.post("/buscar")
def buscar_rota(dados: BuscaIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    from app.modules.ai_registry.cliente import AiCallError
    from app.modules.ai_registry.servico import SemConexaoIA
    from app.modules.rag.rag import buscar

    try:
        return {"resultados": buscar(db, dados.consulta, dados.colecao)}
    except SemConexaoIA as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AiCallError as e:
        raise HTTPException(status_code=502, detail=f"Embeddings falharam: {e}") from e
