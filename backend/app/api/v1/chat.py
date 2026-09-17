"""Chat de estudo: conversas e mensagens. Tutor especialista do caderno.

Uso protegido pela porta de acesso diária ([099], admin/vitalício livres) e
pelo guardrail de orçamento (imposto no motor de IA). O gabarito nunca é
decidido pelo LLM.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import usuario_atual
from app.db.models import ChatMessage, Conversation, RagDocument, User
from app.db.session import get_db
from app.modules.ai_registry import limites
from app.modules.ai_registry.cliente import AiCallError
from app.modules.ai_registry.servico import SemConexaoIA
from app.modules.chat.chat import responder, responder_e_falar, transcrever_pergunta
from app.modules.creditos import acesso_diario
from app.modules.creditos.carteira import saldo
from app.modules.features import features
from app.modules.youtube.youtube import YoutubeError
from app.modules.youtube.youtube import buscar as buscar_videos

router = APIRouter(prefix="/chat")


def _isento(user: User) -> bool:
    """Só o dono escapa dos limites rolantes. O vitalício não paga crédito, mas
    continua com ritmo limitado — é para isso que o limite existe."""
    return user.role == "superadmin"


MODOS_CONVERSA = ("chat", "tutor")  # [109]: "chat" = tutor do caderno; "tutor" = especialista geral (aba Tutor IA)
PERSONAS = ("professor", "amigo")
MODOS_QUESTAO = ("normal", "random")  # [115]: normal = aluno escolhe; random = backend sorteia
# [151]: as únicas 3 vozes de português do Kokoro-82M confirmadas na fonte
# primária (VOICES.md do modelo no Hugging Face, [095]) — não expõe vozes de
# outro idioma pra não confundir o aluno, nem inventa nenhuma além destas.
VOZES_KOKORO = {
    "pf_dora": "Dora (feminina)",
    "pm_alex": "Alex (masculina)",
    "pm_santa": "Santa (masculina)",
}


class NovaConversaIn(BaseModel):
    exam_id: int | None = None  # retrocompatível — usar exam_ids daqui pra frente
    exam_ids: list[int] = []
    titulo: str = "Nova conversa"
    modo: str = "chat"
    persona: str = "professor"
    modo_questao: str = "normal"
    rag_doc_ids: list[int] = []
    modelo_texto_id: int | None = None
    modelo_visao_id: int | None = None
    modelo_voz_id: int | None = None
    modelo_transcricao_id: int | None = None
    modo_voz: bool = False
    voz_escolhida: str | None = None


class ConversaOut(BaseModel):
    id: int
    exam_id: int | None
    exam_ids: list[int] = []
    titulo: str
    modo: str = "chat"
    persona: str = "professor"
    modo_questao: str = "normal"
    rag_doc_ids: list[int] = []
    modelo_texto_id: int | None = None
    modelo_visao_id: int | None = None
    modelo_voz_id: int | None = None
    modelo_transcricao_id: int | None = None
    modo_voz: bool = False
    voz_escolhida: str | None = None


def _saida(c: Conversation) -> ConversaOut:
    return ConversaOut(
        id=c.id, exam_id=c.exam_id, exam_ids=list(c.exam_ids or []), titulo=c.titulo,
        modo=c.modo, persona=c.persona, modo_questao=c.modo_questao,
        rag_doc_ids=list(c.rag_doc_ids or []),
        modelo_texto_id=c.modelo_texto_id, modelo_visao_id=c.modelo_visao_id,
        modelo_voz_id=c.modelo_voz_id, modelo_transcricao_id=c.modelo_transcricao_id,
        modo_voz=c.modo_voz, voz_escolhida=c.voz_escolhida,
    )


def _rag_doc_ids_validos(db: Session, ids: list[int], modo: str) -> list[int]:
    """[110]/[115]: nunca confia cegamente na lista que veio do cliente — só
    mantém ids que existem de verdade e estão classificados pra este modo
    (uso_chat no Chat de estudo, uso_tutor no Tutor IA)."""
    if not ids:
        return []
    coluna = RagDocument.uso_chat if modo == "chat" else RagDocument.uso_tutor
    validos = db.execute(select(RagDocument.id).where(RagDocument.id.in_(ids), coluna.is_(True))).scalars().all()
    return list(validos)


def _dono(conversa: Conversation, user: User) -> bool:
    return conversa.user_id == user.id or user.role == "superadmin"


@router.get("/conversas", response_model=list[ConversaOut])
def listar(modo: str = "chat", user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """`modo` separa as conversas do Chat de estudos das do Tutor IA ([109]) —
    mesma tabela, duas telas diferentes. Default "chat" preserva o comportamento
    de sempre pra quem já usava o Chat de estudos."""
    q = (
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.modo == modo)
        .order_by(Conversation.atualizado_em.desc())
    )
    return [_saida(c) for c in db.execute(q).scalars()]


CATEGORIAS_CHAT = ("texto", "visao", "voz", "transcricao")


@router.get("/modelos")
def modelos_disponiveis(_: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Modelos que o aluno pode escolher, por categoria: texto, visão, voz
    (TTS) e transcrição (STT) — todas as 4 executadas de verdade desde o
    [095]. Só id/nome/modelo — endpoint e chave nunca saem daqui."""
    from app.db.models import AiConnection

    saida: dict[str, list[dict]] = {c: [] for c in CATEGORIAS_CHAT}
    q = select(AiConnection).where(AiConnection.categoria.in_(CATEGORIAS_CHAT))
    for c in db.execute(q).scalars():
        saida[c.categoria].append({"id": c.id, "nome": c.nome, "modelo": c.modelo, "ativa": c.ativa})
    return saida


@router.get("/vozes")
def vozes_disponiveis(_: User = Depends(usuario_atual)):
    """[151]: catálogo das vozes do Kokoro (TTS) que o aluno pode escolher por
    conversa — id + rótulo, pronto pra UI. Fixo (não vem de API nenhuma — a
    Together não expõe lista de vozes por modelo; são as 3 confirmadas na
    fonte primária do modelo, [095])."""
    return [{"id": k, "rotulo": v} for k, v in VOZES_KOKORO.items()]


class DocChatOut(BaseModel):
    id: int
    titulo: str
    descricao: str
    indexado: bool
    tentativas_indexacao: int


@router.get("/documentos-rag", response_model=list[DocChatOut])
def documentos_rag(_: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """[115]: documentos classificados "Chat de estudos" (uso_chat=true) —
    pra escolher como fonte de conhecimento extra numa conversa (paralelo a
    `GET /tutor/documentos`, que é a mesma coisa pra uso_tutor)."""
    docs = db.execute(select(RagDocument).where(RagDocument.uso_chat.is_(True)).order_by(RagDocument.id)).scalars()
    return [
        DocChatOut(id=d.id, titulo=d.titulo, descricao=d.descricao,
                  indexado=d.indexado_em is not None, tentativas_indexacao=d.tentativas_indexacao)
        for d in docs
    ]


@router.get("/limites")
def meus_limites(user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Quanto resta na sessão de 5h e na semana — o aluno vê o próprio ritmo."""
    return limites.estado(db, user.id, isento=_isento(user))


@router.post("/conversas", response_model=ConversaOut, status_code=201)
def criar(dados: NovaConversaIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Criar a conversa já é "usar" o chat ([103]) — atrás da porta diária.
    A lista de conversas existentes (`listar`) continua livre; quem já pagou
    hoje não é cobrado de novo."""
    if motivo := acesso_diario.abrir(db, user):
        raise HTTPException(status_code=402, detail=motivo)
    if dados.modo not in MODOS_CONVERSA:
        raise HTTPException(status_code=422, detail=f"modo inválido — use um de {MODOS_CONVERSA}")
    if dados.persona not in PERSONAS:
        raise HTTPException(status_code=422, detail=f"persona inválida — use uma de {PERSONAS}")
    if dados.modo_questao not in MODOS_QUESTAO:
        raise HTTPException(status_code=422, detail=f"modo_questao inválido — use um de {MODOS_QUESTAO}")
    if dados.voz_escolhida is not None and dados.voz_escolhida not in VOZES_KOKORO:
        raise HTTPException(status_code=422, detail=f"voz inválida — use uma de {list(VOZES_KOKORO)}")
    # [115]: exam_ids é a lista nova; exam_id singular continua aceito por
    # retrocompatibilidade (vira [exam_id] se exam_ids não vier preenchido).
    exam_ids = list(dados.exam_ids) if dados.exam_ids else ([dados.exam_id] if dados.exam_id else [])
    if dados.modo_questao == "random" and not exam_ids:
        raise HTTPException(status_code=422, detail="Modo aleatório precisa de pelo menos um caderno escolhido.")
    c = Conversation(user_id=user.id, exam_id=exam_ids[0] if len(exam_ids) == 1 else None, exam_ids=exam_ids,
                     titulo=dados.titulo.strip() or "Nova conversa",
                     modo=dados.modo, persona=dados.persona, modo_questao=dados.modo_questao,
                     rag_doc_ids=_rag_doc_ids_validos(db, dados.rag_doc_ids, dados.modo),
                     modelo_texto_id=dados.modelo_texto_id, modelo_visao_id=dados.modelo_visao_id,
                     modelo_voz_id=dados.modelo_voz_id, modelo_transcricao_id=dados.modelo_transcricao_id,
                     modo_voz=dados.modo_voz, voz_escolhida=dados.voz_escolhida)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _saida(c)


class EditarConversaIn(BaseModel):
    titulo: str | None = None
    persona: str | None = None
    rag_doc_ids: list[int] | None = None
    modelo_texto_id: int | None = None
    modelo_visao_id: int | None = None
    modelo_voz_id: int | None = None
    modelo_transcricao_id: int | None = None
    modo_voz: bool | None = None
    voz_escolhida: str | None = None
    # [151]: `voz_escolhida=None` no payload é ambíguo (campo ausente ou "voltar
    # ao padrão"?) — este flag explícito distingue "não mexer" de "limpar".
    limpar_voz: bool = False


_CAMPOS_MODELO = ("modelo_texto_id", "modelo_visao_id", "modelo_voz_id", "modelo_transcricao_id")


@router.patch("/conversas/{cid}", response_model=ConversaOut)
def editar(cid: int, dados: EditarConversaIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Troca o título ou como a conversa é atendida: qual IA por categoria e o
    modo (texto/voz)."""
    c = db.get(Conversation, cid)
    if not c or not _dono(c, user):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    if dados.titulo is not None and dados.titulo.strip():
        c.titulo = dados.titulo.strip()[:200]
    if dados.persona is not None:
        if dados.persona not in PERSONAS:
            raise HTTPException(status_code=422, detail=f"persona inválida — use uma de {PERSONAS}")
        c.persona = dados.persona
    if dados.rag_doc_ids is not None:
        c.rag_doc_ids = _rag_doc_ids_validos(db, dados.rag_doc_ids, c.modo)
    for campo in _CAMPOS_MODELO:
        valor = getattr(dados, campo)
        if valor is not None:
            setattr(c, campo, valor or None)
    if dados.limpar_voz:
        c.voz_escolhida = None
    elif dados.voz_escolhida is not None:
        if dados.voz_escolhida not in VOZES_KOKORO:
            raise HTTPException(status_code=422, detail=f"voz inválida — use uma de {list(VOZES_KOKORO)}")
        c.voz_escolhida = dados.voz_escolhida
    if dados.modo_voz is not None:
        c.modo_voz = dados.modo_voz
    db.commit()
    db.refresh(c)
    return _saida(c)


@router.get("/conversas/{cid}")
def mensagens(cid: int, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    c = db.get(Conversation, cid)
    if not c or not _dono(c, user):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    msgs = db.execute(
        select(ChatMessage).where(ChatMessage.conversation_id == cid).order_by(ChatMessage.id)
    ).scalars()
    from app.modules.chat.chat import _exam_ids_efetivos

    return {
        "id": c.id, "exam_id": c.exam_id, "exam_ids": _exam_ids_efetivos(c), "titulo": c.titulo,
        "modo": c.modo, "modo_questao": c.modo_questao,
        "modelo_texto_id": c.modelo_texto_id, "modelo_visao_id": c.modelo_visao_id,
        "modelo_voz_id": c.modelo_voz_id, "modelo_transcricao_id": c.modelo_transcricao_id,
        "modo_voz": c.modo_voz, "voz_escolhida": c.voz_escolhida,
        "mensagens": [{"role": m.role, "conteudo": m.conteudo, "question_id": m.question_id} for m in msgs],
    }


@router.delete("/conversas/{cid}", status_code=204)
def apagar(cid: int, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    c = db.get(Conversation, cid)
    if c and _dono(c, user):
        db.delete(c)
        db.commit()


MAX_IMAGEM_B64 = 8_000_000  # ~6 MB de imagem; acima disso o modelo de visão engasga


class MensagemIn(BaseModel):
    texto: str
    question_id: int | None = None
    imagem_b64: str | None = None  # anexo do aluno, sem o prefixo data:


@router.post("/conversas/{cid}/mensagem")
def enviar(cid: int, dados: MensagemIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    c = db.get(Conversation, cid)
    if not c or not _dono(c, user):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    if not dados.texto.strip():
        raise HTTPException(status_code=422, detail="Escreva a mensagem.")
    if dados.imagem_b64 and len(dados.imagem_b64) > MAX_IMAGEM_B64:
        raise HTTPException(status_code=413, detail="Imagem grande demais. Use uma de até ~6 MB.")

    # limites rolantes de uso (sessão de 5h + semana de 7 dias), estilo plataforma de estudo
    if motivo := limites.bloqueio(db, user.id, isento=_isento(user)):
        raise HTTPException(status_code=429, detail=motivo)

    # acesso diário (porta única — [099]): abre sozinho no 1º uso do dia
    if motivo := acesso_diario.abrir(db, user):
        raise HTTPException(status_code=402, detail=motivo)

    try:
        resposta = responder(db, c, dados.texto.strip(), dados.question_id, dados.imagem_b64)
    except SemConexaoIA as e:  # inclui OrcamentoExcedido
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AiCallError as e:
        raise HTTPException(status_code=502, detail=f"IA falhou: {e}") from e

    db.add(ChatMessage(conversation_id=cid, role="user", conteudo=dados.texto.strip(), question_id=dados.question_id))
    db.add(ChatMessage(conversation_id=cid, role="assistant", conteudo=resposta))
    if c.titulo == "Nova conversa":
        c.titulo = dados.texto.strip()[:60]
    db.commit()

    return {
        "resposta": resposta,
        "saldo": saldo(db, user.id),
        "limites": limites.estado(db, user.id, isento=_isento(user)),
    }


MAX_AUDIO_BYTES = 15_000_000  # ~15 MB — generoso para uma pergunta falada


@router.post("/conversas/{cid}/audio")
async def enviar_audio(cid: int, file: UploadFile = File(...), question_id: int | None = Form(None),
                       user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Chat por voz: grava→transcreve→responde→fala. Custo é a porta diária
    ([099]) — checada ANTES até da transcrição, pra não gastar nada se o
    aluno não tem acesso aberto hoje e não tem crédito pra abrir."""
    c = db.get(Conversation, cid)
    if not c or not _dono(c, user):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="Áudio vazio.")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Áudio grande demais (máx. ~15 MB).")

    if motivo := limites.bloqueio(db, user.id, isento=_isento(user)):
        raise HTTPException(status_code=429, detail=motivo)

    if motivo := acesso_diario.abrir(db, user):
        raise HTTPException(status_code=402, detail=motivo)

    try:
        transcricao = transcrever_pergunta(db, c, audio_bytes, file.filename or "audio.webm")
    except SemConexaoIA as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AiCallError as e:
        raise HTTPException(status_code=502, detail=f"Transcrição falhou: {e}") from e

    try:
        resultado = responder_e_falar(db, c, transcricao["texto"], question_id)
    except SemConexaoIA as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AiCallError as e:
        raise HTTPException(status_code=502, detail=f"IA falhou: {e}") from e

    db.add(ChatMessage(conversation_id=cid, role="user", conteudo=transcricao["texto"], question_id=question_id))
    db.add(ChatMessage(conversation_id=cid, role="assistant", conteudo=resultado["resposta"]))
    if c.titulo == "Nova conversa":
        c.titulo = transcricao["texto"][:60]
    db.commit()

    return {
        "transcricao": transcricao["texto"],
        "resposta": resultado["resposta"],
        "audio_b64": resultado["audio_b64"],
        "saldo": saldo(db, user.id),
        "limites": limites.estado(db, user.id, isento=_isento(user)),
    }


class MensagemFaladaIn(BaseModel):
    texto: str
    question_id: int | None = None


@router.post("/conversas/{cid}/mensagem-falada")
def enviar_com_fala(cid: int, dados: MensagemFaladaIn,
                    user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """[123]: mesma resposta de `/mensagem` (texto digitado), mas TAMBÉM fala
    (TTS) — pro modo carro falar de volta mesmo quando o aluno digita em vez
    de usar o microfone (antes só `/audio`, que exige gravação, disparava
    voz; digitar com o modo carro ligado voltava calado). Mesmos gates de
    `/mensagem`/`/audio` (limites rolantes + porta diária)."""
    c = db.get(Conversation, cid)
    if not c or not _dono(c, user):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    if not dados.texto.strip():
        raise HTTPException(status_code=422, detail="Escreva a mensagem.")

    if motivo := limites.bloqueio(db, user.id, isento=_isento(user)):
        raise HTTPException(status_code=429, detail=motivo)

    if motivo := acesso_diario.abrir(db, user):
        raise HTTPException(status_code=402, detail=motivo)

    try:
        resultado = responder_e_falar(db, c, dados.texto.strip(), dados.question_id)
    except SemConexaoIA as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AiCallError as e:
        raise HTTPException(status_code=502, detail=f"IA falhou: {e}") from e

    db.add(ChatMessage(conversation_id=cid, role="user", conteudo=dados.texto.strip(), question_id=dados.question_id))
    db.add(ChatMessage(conversation_id=cid, role="assistant", conteudo=resultado["resposta"]))
    if c.titulo == "Nova conversa":
        c.titulo = dados.texto.strip()[:60]
    db.commit()

    return {
        "resposta": resultado["resposta"],
        "audio_b64": resultado["audio_b64"],
        "saldo": saldo(db, user.id),
        "limites": limites.estado(db, user.id, isento=_isento(user)),
    }


class VideosIn(BaseModel):
    termo: str


RECURSO_VIDEOS = "youtube_videos"


@router.get("/recursos")
def meus_recursos(user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """O que este usuário pode usar de recursos restritos, e quanto resta hoje —
    para o front decidir se mostra o botão, sem botão morto."""
    return features.recursos_do_usuario(db, user)


@router.post("/videos")
def videos_reais(dados: VideosIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Busca REAL no YouTube para um termo sugerido pelo tutor. Não consome
    crédito nem orçamento (não é chamada de IA/Together) — mas é um recurso
    RESTRITO: precisa de liberação do admin e respeita a cota diária dele."""
    if not dados.termo.strip():
        raise HTTPException(status_code=422, detail="Termo vazio.")
    if not features.tem_acesso(db, user, RECURSO_VIDEOS):
        raise HTTPException(status_code=403,
                            detail="Este recurso é liberado pelo administrador conforme o uso na plataforma.")
    if features.excedeu_limite(db, user, RECURSO_VIDEOS):
        lim = features.limite_diario(db, user.id, RECURSO_VIDEOS)
        raise HTTPException(status_code=429, detail=f"Limite diário de {lim} buscas de vídeo atingido. Volta amanhã.")
    try:
        resultados = buscar_videos(db, dados.termo.strip())
    except YoutubeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    features.registrar_uso(db, user.id, RECURSO_VIDEOS)  # conta mesmo para o admin — é cota real do provedor
    return {"resultados": resultados}


@router.post("/conversas/{cid}/questao/{qid}")
def ler_questao(cid: int, qid: int, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Imprime a questão real (texto/imagem + alternativas) na conversa, sem
    chamar IA — leitura pura do banco, custo zero."""
    from app.db.models import Question
    from app.modules.chat.cartoes import texto_questao

    c = db.get(Conversation, cid)
    if not c or not _dono(c, user):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")
    texto = texto_questao(q)
    db.add(ChatMessage(conversation_id=cid, role="assistant", conteudo=texto, question_id=qid))
    db.commit()
    return {"conteudo": texto}


@router.post("/conversas/{cid}/questao-aleatoria")
def questao_aleatoria(cid: int, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """[115]: modo "random" — sorteia uma questão não descartada entre os
    cadernos da conversa e imprime como o `ler_questao` de sempre (zero
    custo de IA, leitura pura do banco)."""
    from app.db.models import Question
    from app.modules.chat.cartoes import texto_questao
    from app.modules.chat.chat import _exam_ids_efetivos

    c = db.get(Conversation, cid)
    if not c or not _dono(c, user):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    exam_ids = _exam_ids_efetivos(c)
    if not exam_ids:
        raise HTTPException(status_code=422, detail="Esta conversa não tem caderno escolhido para sortear.")
    q = db.execute(
        select(Question)
        .where(Question.exam_id.in_(exam_ids), Question.descartada.is_(False))
        .order_by(func.random())
        .limit(1)
    ).scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="Nenhuma questão disponível nesses cadernos.")
    texto = texto_questao(q)
    db.add(ChatMessage(conversation_id=cid, role="assistant", conteudo=texto, question_id=q.id))
    db.commit()
    return {"question_id": q.id, "conteudo": texto}


@router.post("/conversas/{cid}/gemea/{twin_id}")
def ler_gemea(cid: int, twin_id: int, ordem: str = "A",
              user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Imprime a gêmea (sem gabarito) na conversa — sem chamar IA, ela já foi
    gerada pela rota real de gêmeas ([046])."""
    from app.db.models import TwinQuestion
    from app.modules.chat.cartoes import texto_gemea

    c = db.get(Conversation, cid)
    if not c or not _dono(c, user):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    tw = db.get(TwinQuestion, twin_id)
    if not tw or tw.user_id != user.id:
        raise HTTPException(status_code=404, detail="Gêmea não encontrada.")
    texto = texto_gemea(tw, ordem)
    db.add(ChatMessage(conversation_id=cid, role="assistant", conteudo=texto))
    db.commit()
    return {"conteudo": texto}


class RespostaGemeaChatIn(BaseModel):
    letra: str


@router.post("/conversas/{cid}/gemea/{twin_id}/responder")
def responder_gemea_chat(cid: int, twin_id: int, dados: RespostaGemeaChatIn,
                         user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Confere a resposta da gêmea contra o gabarito REAL (recalculado aqui,
    nunca confia no cliente) e imprime a correção na conversa."""
    from app.db.models import TwinQuestion
    from app.modules.chat.cartoes import texto_correcao_gemea

    c = db.get(Conversation, cid)
    if not c or not _dono(c, user):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    tw = db.get(TwinQuestion, twin_id)
    if not tw or tw.user_id != user.id:
        raise HTTPException(status_code=404, detail="Gêmea não encontrada.")
    letra = dados.letra.strip().upper()
    acertou = letra == tw.gabarito
    texto = texto_correcao_gemea(tw, letra, acertou)
    db.add(ChatMessage(conversation_id=cid, role="user", conteudo=f"Minha resposta da gêmea: {letra}"))
    db.add(ChatMessage(conversation_id=cid, role="assistant", conteudo=texto))
    db.commit()
    return {"acertou": acertou, "gabarito": tw.gabarito, "conteudo": texto}


class FechamentoIn(BaseModel):
    letra_principal: str
    gemea_a_ok: bool
    gemea_b_ok: bool


@router.post("/conversas/{cid}/questao/{qid}/fechamento")
def fechamento(cid: int, qid: int, dados: FechamentoIn,
               user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Resumo do ciclo (principal + 2 gêmeas), modo automático. `principal_ok`
    é RECALCULADO aqui contra o gabarito real — nunca confia no cliente pra
    isso. `gemea_a_ok`/`gemea_b_ok` só formatam o resumo (já foram conferidos
    de verdade segundos antes, na rota de corrigir gêmea)."""
    from app.db.models import Question
    from app.modules.chat.cartoes import texto_fechamento
    from app.modules.desempenho.consolidado import mastery_consolidado

    c = db.get(Conversation, cid)
    if not c or not _dono(c, user):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")
    principal_ok = dados.letra_principal.strip().upper() == (q.gabarito or "").upper()
    m = next((x for x in mastery_consolidado(db, user.id) if x["enfase"] == q.disciplina), None)
    texto = texto_fechamento(q.disciplina, principal_ok, dados.gemea_a_ok, dados.gemea_b_ok, m)
    db.add(ChatMessage(conversation_id=cid, role="assistant", conteudo=texto, question_id=qid))
    db.commit()
    return {"conteudo": texto}
