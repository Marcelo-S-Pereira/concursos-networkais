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
    descricao: str
    colecao: str
    chunk_count: int
    indexado: bool
    erro: str | None
    uso_chat: bool
    uso_tutor: bool
    uso_simulado: bool
    enviado_por: str | None  # [109]: nome de quem contribuiu (PDF/vídeo pela aba Tutor IA); None = admin
    tentativas_indexacao: int  # [110]: quantas vezes tentou gerar embedding


def _nome_de(db: Session, user_id: int | None) -> str | None:
    if not user_id:
        return None
    return db.scalar(select(User.nome).where(User.id == user_id))


def _saida(d: RagDocument, db: Session) -> DocOut:
    return DocOut(id=d.id, titulo=d.titulo, descricao=d.descricao, colecao=d.colecao, chunk_count=d.chunk_count,
                  indexado=d.indexado_em is not None, erro=d.erro,
                  uso_chat=d.uso_chat, uso_tutor=d.uso_tutor, uso_simulado=d.uso_simulado,
                  enviado_por=_nome_de(db, d.enviado_por_user_id), tentativas_indexacao=d.tentativas_indexacao)


@router.get("/documentos", response_model=list[DocOut])
def listar(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    docs = db.execute(select(RagDocument).order_by(RagDocument.id)).scalars().all()
    nomes = dict(db.execute(select(User.id, User.nome)).all())
    return [
        DocOut(id=d.id, titulo=d.titulo, descricao=d.descricao, colecao=d.colecao, chunk_count=d.chunk_count,
               indexado=d.indexado_em is not None, erro=d.erro,
               uso_chat=d.uso_chat, uso_tutor=d.uso_tutor, uso_simulado=d.uso_simulado,
               enviado_por=nomes.get(d.enviado_por_user_id), tentativas_indexacao=d.tentativas_indexacao)
        for d in docs
    ]


@router.post("/documentos/importar", response_model=DocOut, status_code=201)
async def importar(
    arquivo: UploadFile,
    titulo: str = Form(""),
    colecao: str = Form("oficial"),
    uso_chat: bool = Form(False),
    uso_tutor: bool = Form(False),
    uso_simulado: bool = Form(False),
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
    doc = ingerir_documento(db, titulo or arquivo.filename or "Documento", texto, colecao=colecao,
                             uso_chat=uso_chat, uso_tutor=uso_tutor, uso_simulado=uso_simulado)
    return _saida(doc, db)


class EditarDocIn(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    uso_chat: bool | None = None
    uso_tutor: bool | None = None
    uso_simulado: bool | None = None


@router.patch("/documentos/{doc_id}", response_model=DocOut)
def editar_documento(
    doc_id: int, dados: EditarDocIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)
):
    """[106]/[108]: título, descrição (a "memória de conhecimento" do que o
    documento trata) e a classificação de uso — em quais ferramentas ele
    pode ser consultado. Cada campo só muda se vier no corpo (None = mantém).
    Não apaga nem reindexa nada."""
    doc = db.get(RagDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    if dados.titulo is not None and dados.titulo.strip():
        doc.titulo = dados.titulo.strip()[:300]
    if dados.descricao is not None:
        doc.descricao = dados.descricao.strip()[:500]
    if dados.uso_chat is not None:
        doc.uso_chat = dados.uso_chat
    if dados.uso_tutor is not None:
        doc.uso_tutor = dados.uso_tutor
    if dados.uso_simulado is not None:
        doc.uso_simulado = dados.uso_simulado
    db.commit()
    return _saida(doc, db)


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
    return _saida(doc, db)


@router.delete("/documentos/{doc_id}", status_code=204)
def apagar(doc_id: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    doc = db.get(RagDocument, doc_id)
    if doc:
        db.delete(doc)
        db.commit()


class BuscaIn(BaseModel):
    consulta: str
    colecao: str | None = None
    uso: str | None = None  # [106]: "chat"|"tutor"|"simulado" — a tela do admin não usa, fica pra quem integrar depois


@router.post("/buscar")
def buscar_rota(dados: BuscaIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    from app.modules.ai_registry.cliente import AiCallError
    from app.modules.ai_registry.servico import SemConexaoIA
    from app.modules.rag.rag import buscar

    try:
        return {"resultados": buscar(db, dados.consulta, dados.colecao, uso=dados.uso)}
    except SemConexaoIA as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AiCallError as e:
        raise HTTPException(status_code=502, detail=f"Embeddings falharam: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


class PerguntaIn(BaseModel):
    pergunta: str
    colecao: str | None = "oficial"
    uso: str | None = None  # [106]: idem BuscaIn


@router.post("/perguntar")
def perguntar_rota(dados: PerguntaIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    from app.modules.ai_registry.cliente import AiCallError
    from app.modules.ai_registry.servico import SemConexaoIA
    from app.modules.rag.rag import perguntar

    if not dados.pergunta.strip():
        raise HTTPException(status_code=422, detail="Escreva a pergunta.")
    try:
        return perguntar(db, dados.pergunta, dados.colecao or "oficial", uso=dados.uso)
    except SemConexaoIA as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AiCallError as e:
        raise HTTPException(status_code=502, detail=f"IA falhou: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
