"""Chat de estudo: conversas e mensagens. Tutor especialista do caderno.

Consome crédito por mensagem (admin/vitalício livres) e respeita o guardrail de
orçamento (imposto no motor de IA). O gabarito nunca é decidido pelo LLM.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import usuario_atual
from app.core.flags import get_flag
from app.db.models import ChatMessage, Conversation, User
from app.db.session import get_db
from app.modules.ai_registry import limites
from app.modules.ai_registry.cliente import AiCallError
from app.modules.ai_registry.servico import SemConexaoIA
from app.modules.chat.chat import responder
from app.modules.creditos.carteira import creditar, saldo
from app.modules.features import features
from app.modules.youtube.youtube import YoutubeError
from app.modules.youtube.youtube import buscar as buscar_videos

router = APIRouter(prefix="/chat")


def _isento(user: User) -> bool:
    """Só o dono escapa dos limites rolantes. O vitalício não paga crédito, mas
    continua com ritmo limitado — é para isso que o limite existe."""
    return user.role == "superadmin"


class NovaConversaIn(BaseModel):
    exam_id: int | None = None
    titulo: str = "Nova conversa"
    modelo_texto_id: int | None = None
    modelo_visao_id: int | None = None
    modelo_voz_id: int | None = None
    modelo_transcricao_id: int | None = None
    modo_voz: bool = False


class ConversaOut(BaseModel):
    id: int
    exam_id: int | None
    titulo: str
    modelo_texto_id: int | None = None
    modelo_visao_id: int | None = None
    modelo_voz_id: int | None = None
    modelo_transcricao_id: int | None = None
    modo_voz: bool = False


def _saida(c: Conversation) -> ConversaOut:
    return ConversaOut(
        id=c.id, exam_id=c.exam_id, titulo=c.titulo,
        modelo_texto_id=c.modelo_texto_id, modelo_visao_id=c.modelo_visao_id,
        modelo_voz_id=c.modelo_voz_id, modelo_transcricao_id=c.modelo_transcricao_id,
        modo_voz=c.modo_voz,
    )


def _dono(conversa: Conversation, user: User) -> bool:
    return conversa.user_id == user.id or user.role == "superadmin"


@router.get("/conversas", response_model=list[ConversaOut])
def listar(user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    q = select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.atualizado_em.desc())
    return [_saida(c) for c in db.execute(q).scalars()]


CATEGORIAS_CHAT = ("texto", "visao", "voz", "transcricao")


@router.get("/modelos")
def modelos_disponiveis(_: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Modelos que o aluno pode escolher, por categoria: texto, visão, voz
    (TTS) e transcrição (STT). Só id/nome/modelo — endpoint e chave nunca saem
    daqui. Voz e transcrição aparecem para SEREM ESCOLHIDAS, mesmo o motor
    ainda não as executando (ver modo_voz)."""
    from app.db.models import AiConnection

    saida: dict[str, list[dict]] = {c: [] for c in CATEGORIAS_CHAT}
    q = select(AiConnection).where(AiConnection.categoria.in_(CATEGORIAS_CHAT))
    for c in db.execute(q).scalars():
        saida[c.categoria].append({"id": c.id, "nome": c.nome, "modelo": c.modelo, "ativa": c.ativa})
    return saida


@router.get("/limites")
def meus_limites(user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Quanto resta na sessão de 5h e na semana — o aluno vê o próprio ritmo."""
    return limites.estado(db, user.id, isento=_isento(user))


@router.post("/conversas", response_model=ConversaOut, status_code=201)
def criar(dados: NovaConversaIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    c = Conversation(user_id=user.id, exam_id=dados.exam_id, titulo=dados.titulo.strip() or "Nova conversa",
                     modelo_texto_id=dados.modelo_texto_id, modelo_visao_id=dados.modelo_visao_id,
                     modelo_voz_id=dados.modelo_voz_id, modelo_transcricao_id=dados.modelo_transcricao_id,
                     modo_voz=dados.modo_voz)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _saida(c)


class EditarConversaIn(BaseModel):
    titulo: str | None = None
    modelo_texto_id: int | None = None
    modelo_visao_id: int | None = None
    modelo_voz_id: int | None = None
    modelo_transcricao_id: int | None = None
    modo_voz: bool | None = None


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
    for campo in _CAMPOS_MODELO:
        valor = getattr(dados, campo)
        if valor is not None:
            setattr(c, campo, valor or None)
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
    return {
        "id": c.id, "exam_id": c.exam_id, "titulo": c.titulo,
        "modelo_texto_id": c.modelo_texto_id, "modelo_visao_id": c.modelo_visao_id,
        "modelo_voz_id": c.modelo_voz_id, "modelo_transcricao_id": c.modelo_transcricao_id,
        "modo_voz": c.modo_voz,
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

    # consumo de crédito (o dono e o vitalício não gastam)
    custo = 0
    if user.role != "superadmin" and not user.vitalicio:
        custo = int(get_flag(db, "pag_creditos_chat", "1"))
        if saldo(db, user.id) < custo:
            raise HTTPException(status_code=402,
                                detail="Créditos insuficientes para o chat. Compre créditos no seu perfil.")

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

    if custo:
        creditar(db, user.id, -custo, "gasto_chat_texto", "mensagem do chat")

    return {
        "resposta": resposta,
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
