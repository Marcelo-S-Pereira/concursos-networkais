"""Contribuições de conhecimento pra o Tutor IA ([109]/[110]): qualquer
usuário (não só admin) pode enviar PDF/Markdown ou um link de vídeo do
YouTube pra virar documento na Biblioteca RAG do admin, com o nome de quem
enviou. Atrás da porta diária, como todo uso do chat/tutor — sem cobrança
extra aqui. `GET /documentos` lista o que está disponível pro Tutor escolher
("em análise" quando ainda não indexou).

[111]: o download server-side de vídeo (`/documentos/video`) é bloqueado pelo
anti-bot do YouTube contra IP de ambiente de execucao — ver `modules/video/transcricao_youtube.py`.
`/documentos/video-audio` é o caminho que funciona: o NAVEGADOR do usuário
reproduz o vídeo pelo embed oficial e grava o áudio da própria aba
(getDisplayMedia) — o servidor aqui só recebe o áudio já gravado e transcreve,
nunca fala com o YouTube."""

import io
import re

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import usuario_atual
from app.db.models import Conversation, RagDocument, User
from app.db.session import get_db
from app.modules.ai_registry import uso
from app.modules.creditos import acesso_diario
from app.modules.youtube import youtube

router = APIRouter(prefix="/tutor")

_ID_YOUTUBE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([a-zA-Z0-9_-]{11})"
)


class DocContribuidoOut(BaseModel):
    id: int
    titulo: str
    descricao: str
    chunk_count: int


class DocDisponivelOut(BaseModel):
    id: int
    titulo: str
    descricao: str
    indexado: bool
    tentativas_indexacao: int
    enviado_por: str | None


@router.get("/documentos", response_model=list[DocDisponivelOut])
def documentos_disponiveis(_: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """[110]: tudo que está classificado "Tutor IA" — pelo admin na
    Biblioteca ou por qualquer usuário enviando aqui — pra escolher numa
    conversa. `indexado=False` = "em análise" (ainda sem embedding)."""
    docs = db.execute(
        select(RagDocument).where(RagDocument.uso_tutor.is_(True)).order_by(RagDocument.id)
    ).scalars().all()
    nomes = dict(db.execute(select(User.id, User.nome)).all())
    return [
        DocDisponivelOut(
            id=d.id, titulo=d.titulo, descricao=d.descricao, indexado=d.indexado_em is not None,
            tentativas_indexacao=d.tentativas_indexacao, enviado_por=nomes.get(d.enviado_por_user_id),
        )
        for d in docs
    ]


def _anexar_a_conversa(db: Session, user: User, conversation_id: int | None, doc_id: int) -> None:
    """[110]: anexar direto de dentro de uma conversa já deixa o documento
    novo disponível ali, sem passo extra. Só afeta a própria conversa do
    usuário, modo "tutor"; qualquer outra combinação é ignorada em silêncio
    (não é erro do upload, só não auto-seleciona)."""
    if not conversation_id:
        return
    c = db.get(Conversation, conversation_id)
    if not c or c.user_id != user.id or c.modo != "tutor":
        return
    ids = list(c.rag_doc_ids or [])
    if doc_id not in ids:
        ids.append(doc_id)
        c.rag_doc_ids = ids
        db.commit()


EXTENSOES_TEXTO = (".md", ".markdown", ".txt")


def _extrair_texto(nome: str, content_type: str, dados: bytes) -> str:
    nome_lower = (nome or "").lower()
    if content_type == "application/pdf" or nome_lower.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(dados))
        return "\n\n".join((p.extract_text() or "") for p in reader.pages)
    if content_type in ("text/markdown", "text/plain") or nome_lower.endswith(EXTENSOES_TEXTO):
        return dados.decode("utf-8", errors="ignore")
    raise HTTPException(
        status_code=422, detail=f"Formato não suportado: {nome or content_type}. Envie PDF ou .md/.txt."
    )


@router.post("/documentos/arquivo", response_model=list[DocContribuidoOut], status_code=201)
async def enviar_arquivos(
    arquivos: list[UploadFile], conversation_id: int | None = Form(None),
    user: User = Depends(usuario_atual), db: Session = Depends(get_db),
):
    """[110]: um ou vários arquivos de uma vez (PDF ou Markdown/texto) — cada
    um vira um documento na Biblioteca do admin, com a autoria do usuário.
    Outros formatos (docx etc.) ainda não são suportados — dito com clareza,
    não fingido. `conversation_id` opcional já anexa à conversa ativa."""
    if motivo := acesso_diario.abrir(db, user):
        raise HTTPException(status_code=402, detail=motivo)
    uso.marcar(ferramenta="tutor_ia")  # [170] o custo do envio é do Tutor IA, de quem enviou

    from app.modules.rag.rag import ingerir_documento

    saida: list[DocContribuidoOut] = []
    for arquivo in arquivos:
        dados = await arquivo.read()
        if len(dados) > 32_000_000:
            raise HTTPException(status_code=413, detail=f"{arquivo.filename}: arquivo grande demais (máx 32MB).")
        texto = _extrair_texto(arquivo.filename or "", arquivo.content_type or "", dados)
        if not texto.strip():
            raise HTTPException(
                status_code=422, detail=f"{arquivo.filename}: sem texto extraível (imagem escaneada?)."
            )
        doc = ingerir_documento(
            db, arquivo.filename or "Documento", texto, colecao="tutor_usuarios",
            uso_tutor=True, enviado_por_user_id=user.id,
        )
        _anexar_a_conversa(db, user, conversation_id, doc.id)
        saida.append(
            DocContribuidoOut(id=doc.id, titulo=doc.titulo, descricao=doc.descricao, chunk_count=doc.chunk_count)
        )
    return saida


class VideoIn(BaseModel):
    url: str
    conversation_id: int | None = None


@router.post("/documentos/video", response_model=DocContribuidoOut, status_code=201)
def enviar_video(dados: VideoIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Link de vídeo do YouTube ESCOLHIDO PELO USUÁRIO (manual) — baixa o
    áudio, transcreve (Whisper) e vira documento na Biblioteca, classificado
    pra "Tutor IA", com a autoria dele. Hoje o YouTube bloqueia download vindo
    desta ambiente de execucao (achado real, ver `transcricao_youtube.py`) — o erro que volta
    é o real, não fingido."""
    if motivo := acesso_diario.abrir(db, user):
        raise HTTPException(status_code=402, detail=motivo)
    uso.marcar(ferramenta="tutor_ia")  # [170] o custo do envio é do Tutor IA, de quem enviou

    from app.modules.ai_registry.cliente import AiCallError
    from app.modules.ai_registry.servico import SemConexaoIA
    from app.modules.rag.rag import ingerir_documento
    from app.modules.video.transcricao_youtube import VideoError, transcrever_link

    try:
        resultado = transcrever_link(db, dados.url, user_id=user.id)
    except VideoError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except SemConexaoIA as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AiCallError as e:
        raise HTTPException(status_code=502, detail=f"A transcrição falhou: {e}") from e

    doc = ingerir_documento(
        db, resultado["titulo"], resultado["texto"], colecao="tutor_usuarios",
        uso_tutor=True, enviado_por_user_id=user.id,
    )
    _anexar_a_conversa(db, user, dados.conversation_id, doc.id)
    return DocContribuidoOut(id=doc.id, titulo=doc.titulo, descricao=doc.descricao, chunk_count=doc.chunk_count)


def _titulo_via_oembed(url: str) -> str | None:
    """Título real do vídeo via oEmbed do YouTube — endpoint PÚBLICO, sem
    chave, feito oficialmente pra quem embeda vídeo (não é scraping). Só
    cosmético: falha aqui nunca derruba o upload, só usa um título genérico."""
    try:
        r = httpx.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"}, timeout=6)
        if r.status_code == 200:
            titulo = r.json().get("title")
            if titulo and titulo.strip():
                return titulo.strip()
    except Exception:  # noqa: BLE001
        pass
    return None


class VideoInfoOut(BaseModel):
    titulo: str | None
    duracao_s: int | None


@router.get("/video-info", response_model=VideoInfoOut)
def video_info(url: str, _: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """[113]: título + duração real do vídeo, pra mostrar UMA ESTIMATIVA de
    quanto tempo a gravação vai levar (o vídeo toca em tempo real na aba do
    usuário) — nunca sobe/baixa nada do YouTube, só metadado público. Duração
    fica None sem a chave da YouTube Data API cadastrada ([083]) ou se o
    vídeo não for encontrado — nunca inventa número. Gratuito: não gasta
    porta diária nem crédito (mesmo critério do oEmbed acima)."""
    m = _ID_YOUTUBE.search(url)
    video_id = m.group(1) if m else None
    return VideoInfoOut(
        titulo=_titulo_via_oembed(url),
        duracao_s=youtube.duracao_video(db, video_id) if video_id else None,
    )


MAX_AUDIO_VIDEO_BYTES = 75_000_000  # a Together aceita até 80MB de upload direto


@router.post("/documentos/video-audio", response_model=DocContribuidoOut, status_code=201)
async def enviar_video_audio(
    file: UploadFile, url: str = Form(...), titulo: str | None = Form(None),
    conversation_id: int | None = Form(None),
    user: User = Depends(usuario_atual), db: Session = Depends(get_db),
):
    """[111]: alternativa que FUNCIONA ao download server-side (bloqueado
    pelo YouTube, ver `/documentos/video` acima) — o navegador do usuário
    reproduz o vídeo pelo embed oficial e grava o áudio da própria aba
    (getDisplayMedia); aqui só chega o áudio já gravado. Nunca falamos com o
    YouTube pra baixar nada — só pro oEmbed do título, que é público e feito
    pra isso."""
    if motivo := acesso_diario.abrir(db, user):
        raise HTTPException(status_code=402, detail=motivo)
    uso.marcar(ferramenta="tutor_ia")  # [170] o custo do envio é do Tutor IA, de quem enviou

    dados = await file.read()
    if not dados:
        raise HTTPException(status_code=422, detail="Áudio vazio — a gravação não capturou nada.")
    if len(dados) > MAX_AUDIO_VIDEO_BYTES:
        raise HTTPException(status_code=413, detail="Áudio grande demais (máx. ~75 MB) — grave um trecho menor.")

    from app.modules.ai_registry.cliente import AiCallError
    from app.modules.ai_registry.servico import SemConexaoIA, transcrever_audio
    from app.modules.rag.rag import ingerir_documento

    try:
        resultado = transcrever_audio(
            db, dados, file.filename or "video.webm", origem="tutor_video_navegador", user_id=user.id,
        )
    except SemConexaoIA as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AiCallError as e:
        raise HTTPException(status_code=502, detail=f"A transcrição falhou: {e}") from e

    texto = resultado["texto"].strip()
    if not texto:
        raise HTTPException(
            status_code=422,
            detail="Não identifiquei fala no áudio gravado — confira se o vídeo estava tocando com som.",
        )

    titulo_final = (titulo or "").strip() or _titulo_via_oembed(url) or f"Vídeo: {url}"
    doc = ingerir_documento(
        db, titulo_final, texto, colecao="tutor_usuarios", uso_tutor=True, enviado_por_user_id=user.id,
    )
    _anexar_a_conversa(db, user, conversation_id, doc.id)
    return DocContribuidoOut(id=doc.id, titulo=doc.titulo, descricao=doc.descricao, chunk_count=doc.chunk_count)
