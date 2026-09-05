"""Painel de conexões de IA (só superadmin). LLM/VLM/STT/TTS/embeddings.

Segue o padrão do network-ais: chave cifrada no banco, listagem só com a chave
mascarada, revelar em rota separada e explícita, chave em branco na edição
mantém a atual. Ordem de fallback numerada; ativa é a posição 1 da categoria.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import apenas_superadmin
from app.core.crypto import cifrar_ia, decifrar_ia, mascarar_chave
from app.db.models import AiConnection, AiPlatform, User
from app.db.session import get_db
from app.modules.ai_registry import cliente, resolver

router = APIRouter(prefix="/ai/conexoes")

CATEGORIAS_VALIDAS = {"texto", "visao", "embeddings", "transcricao", "voz"}


class ConexaoIn(BaseModel):
    """Um MODELO. Endpoint e chave não vêm aqui — moram na plataforma."""

    platform_id: int
    nome: str = Field(min_length=1, max_length=120)
    modelo: str = Field(min_length=1, max_length=200)
    categoria: str
    tipo_deploy: str = "serverless"
    max_tokens: int = 4000
    temperatura: float = 0.7
    context_window_tokens: int | None = None
    rate_limit_rpm: int | None = None
    preco_entrada_por_milhao: float | None = None
    preco_saida_por_milhao: float | None = None
    moeda: str = "USD"


class ConexaoOut(BaseModel):
    id: int
    platform_id: int
    plataforma_titulo: str
    nome: str
    modelo: str
    categoria: str
    tipo_deploy: str
    ativa: bool
    ordem_fallback: int | None
    max_tokens: int
    temperatura: float
    context_window_tokens: int | None
    rate_limit_rpm: int | None
    preco_entrada_por_milhao: float | None
    preco_saida_por_milhao: float | None
    moeda: str


def _saida(c: AiConnection) -> ConexaoOut:
    return ConexaoOut(
        id=c.id, platform_id=c.platform_id, plataforma_titulo=c.plataforma.titulo,
        nome=c.nome, modelo=c.modelo, categoria=c.categoria,
        tipo_deploy=c.tipo_deploy, ativa=c.ativa, ordem_fallback=c.ordem_fallback,
        max_tokens=c.max_tokens, temperatura=c.temperatura,
        context_window_tokens=c.context_window_tokens, rate_limit_rpm=c.rate_limit_rpm,
        preco_entrada_por_milhao=c.preco_entrada_por_milhao, preco_saida_por_milhao=c.preco_saida_por_milhao,
        moeda=c.moeda,
    )


def _validar_categoria(cat: str) -> None:
    if cat not in CATEGORIAS_VALIDAS:
        validas = ", ".join(sorted(CATEGORIAS_VALIDAS))
        raise HTTPException(status_code=422, detail=f"Categoria inválida. Use: {validas}.")


@router.get("", response_model=list[ConexaoOut])
def listar(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    conns = db.execute(
        select(AiConnection).order_by(AiConnection.categoria, AiConnection.ativa.desc(), AiConnection.ordem_fallback)
    ).scalars()
    return [_saida(c) for c in conns]


@router.post("", response_model=ConexaoOut, status_code=201)
def criar(dados: ConexaoIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    _validar_categoria(dados.categoria)
    # se for a primeira da categoria, nasce ativa
    ja_tem = db.execute(select(AiConnection).where(AiConnection.categoria == dados.categoria)).first()
    if not db.get(AiPlatform, dados.platform_id):
        raise HTTPException(status_code=404, detail="Plataforma não encontrada.")
    conn = AiConnection(
        platform_id=dados.platform_id,
        nome=dados.nome, modelo=dados.modelo, categoria=dados.categoria, tipo_deploy=dados.tipo_deploy,
        ativa=not ja_tem, max_tokens=dados.max_tokens, temperatura=dados.temperatura,
        context_window_tokens=dados.context_window_tokens, rate_limit_rpm=dados.rate_limit_rpm,
        preco_entrada_por_milhao=dados.preco_entrada_por_milhao,
        preco_saida_por_milhao=dados.preco_saida_por_milhao, moeda=dados.moeda,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    resolver.invalidar_cache()
    return _saida(conn)


@router.patch("/{cid}", response_model=ConexaoOut)
def editar(cid: int, dados: ConexaoIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    conn = db.get(AiConnection, cid)
    if not conn:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    _validar_categoria(dados.categoria)
    if not db.get(AiPlatform, dados.platform_id):
        raise HTTPException(status_code=404, detail="Plataforma não encontrada.")
    conn.platform_id, conn.nome, conn.modelo = dados.platform_id, dados.nome, dados.modelo
    conn.categoria, conn.tipo_deploy = dados.categoria, dados.tipo_deploy
    conn.max_tokens, conn.temperatura = dados.max_tokens, dados.temperatura
    conn.context_window_tokens, conn.rate_limit_rpm = dados.context_window_tokens, dados.rate_limit_rpm
    conn.preco_entrada_por_milhao = dados.preco_entrada_por_milhao
    conn.preco_saida_por_milhao = dados.preco_saida_por_milhao
    conn.moeda = dados.moeda
    db.commit()
    db.refresh(conn)
    resolver.invalidar_cache()
    return _saida(conn)


@router.delete("/{cid}", status_code=204)
def apagar(cid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    conn = db.get(AiConnection, cid)
    if conn:
        db.delete(conn)
        db.commit()
        resolver.invalidar_cache()


@router.post("/{cid}/ativar", response_model=list[ConexaoOut])
def ativar(cid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    conn = db.get(AiConnection, cid)
    if not conn:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    for outra in db.execute(select(AiConnection).where(AiConnection.categoria == conn.categoria)).scalars():
        outra.ativa = outra.id == cid
    db.commit()
    resolver.invalidar_cache()
    return listar(_, db)


class FallbackIn(BaseModel):
    ordem: int | None  # None remove da cadeia de fallback


@router.post("/{cid}/fallback", response_model=list[ConexaoOut])
def definir_fallback(cid: int, dados: FallbackIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    conn = db.get(AiConnection, cid)
    if not conn:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    conn.ordem_fallback = dados.ordem
    db.commit()
    resolver.invalidar_cache()
    return listar(_, db)


@router.post("/{cid}/testar")
def testar(cid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    conn = db.get(AiConnection, cid)
    if not conn:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    try:
        if conn.categoria in ("texto", "visao"):
            conteudo, usage = cliente.chamar_chat(
                conn, [{"role": "user", "content": "Responda apenas OK."}], max_tokens=20
            )
            return {"ok": True, "resposta": conteudo[:120], "usage": usage}
        if conn.categoria == "embeddings":
            vetores, usage = cliente.chamar_embeddings(conn, ["teste"])
            return {"ok": True, "dimensao": len(vetores[0]), "usage": usage}
        return {
            "ok": None,
            "resposta": f"Teste automático de '{conn.categoria}' precisa de áudio — conexão salva, teste manual.",
        }
    except cliente.AiCallError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Plataformas: Together, Anthropic, OpenAI, Grok, OpenRouter, HuggingFace...
# Endpoint e chave moram aqui, uma vez só; os modelos herdam.
# ---------------------------------------------------------------------------

router_plataformas = APIRouter(prefix="/ai/plataformas")


class PlataformaIn(BaseModel):
    titulo: str = Field(min_length=1, max_length=120)
    endpoint: str = Field(min_length=1, max_length=500)
    api_key: str = ""  # em branco na edição = mantém a atual


class PlataformaOut(BaseModel):
    id: int
    titulo: str
    endpoint: str
    chave_mascarada: str
    qtd_modelos: int


def _saida_plataforma(p: AiPlatform) -> PlataformaOut:
    return PlataformaOut(
        id=p.id, titulo=p.titulo, endpoint=p.endpoint,
        chave_mascarada=mascarar_chave(decifrar_ia(p.api_key_cifrada)) if p.api_key_cifrada else "",
        qtd_modelos=len(p.modelos),
    )


@router_plataformas.get("", response_model=list[PlataformaOut])
def listar_plataformas(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    return [_saida_plataforma(p) for p in db.execute(select(AiPlatform).order_by(AiPlatform.id)).unique().scalars()]


@router_plataformas.post("", response_model=PlataformaOut, status_code=201)
def criar_plataforma(dados: PlataformaIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    p = AiPlatform(titulo=dados.titulo, endpoint=dados.endpoint, api_key_cifrada=cifrar_ia(dados.api_key))
    db.add(p)
    db.commit()
    db.refresh(p)
    return _saida_plataforma(p)


@router_plataformas.patch("/{pid}", response_model=PlataformaOut)
def editar_plataforma(pid: int, dados: PlataformaIn, _: User = Depends(apenas_superadmin),
                      db: Session = Depends(get_db)):
    p = db.get(AiPlatform, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Plataforma não encontrada.")
    p.titulo, p.endpoint = dados.titulo, dados.endpoint
    if dados.api_key.strip():  # em branco = mantém a atual
        p.api_key_cifrada = cifrar_ia(dados.api_key)
    db.commit()
    db.refresh(p)
    resolver.invalidar_cache()  # a chave/endpoint mudou para todos os modelos filhos
    return _saida_plataforma(p)


@router_plataformas.delete("/{pid}", status_code=204)
def apagar_plataforma(pid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Apaga a plataforma E os modelos dela (cascade). Recusa se ainda houver
    modelo cadastrado, para o clique não levar junto o que não se pretendia."""
    p = db.get(AiPlatform, pid)
    if not p:
        return
    if p.modelos:
        raise HTTPException(
            status_code=409,
            detail=f"'{p.titulo}' ainda tem {len(p.modelos)} modelo(s). Apague os modelos antes.",
        )
    db.delete(p)
    db.commit()
    resolver.invalidar_cache()


@router_plataformas.get("/{pid}/revelar")
def revelar_chave_plataforma(pid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    p = db.get(AiPlatform, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Plataforma não encontrada.")
    return {"api_key": decifrar_ia(p.api_key_cifrada)}
