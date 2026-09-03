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
from app.db.models import AiConnection, User
from app.db.session import get_db
from app.modules.ai_registry import cliente, resolver

router = APIRouter(prefix="/ai/conexoes")

CATEGORIAS_VALIDAS = {"texto", "visao", "embeddings", "transcricao", "voz"}


class ConexaoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    endpoint: str = Field(min_length=1, max_length=500)
    api_key: str = ""  # em branco na edição = mantém a atual
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
    nome: str
    endpoint: str
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
    chave_mascarada: str


def _saida(c: AiConnection) -> ConexaoOut:
    return ConexaoOut(
        id=c.id, nome=c.nome, endpoint=c.endpoint, modelo=c.modelo, categoria=c.categoria,
        tipo_deploy=c.tipo_deploy, ativa=c.ativa, ordem_fallback=c.ordem_fallback,
        max_tokens=c.max_tokens, temperatura=c.temperatura,
        context_window_tokens=c.context_window_tokens, rate_limit_rpm=c.rate_limit_rpm,
        preco_entrada_por_milhao=c.preco_entrada_por_milhao, preco_saida_por_milhao=c.preco_saida_por_milhao,
        moeda=c.moeda,
        chave_mascarada=mascarar_chave(decifrar_ia(c.api_key_cifrada)) if c.api_key_cifrada else "",
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
    conn = AiConnection(
        nome=dados.nome, endpoint=dados.endpoint, api_key_cifrada=cifrar_ia(dados.api_key),
        modelo=dados.modelo, categoria=dados.categoria, tipo_deploy=dados.tipo_deploy,
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
    conn.nome, conn.endpoint, conn.modelo = dados.nome, dados.endpoint, dados.modelo
    conn.categoria, conn.tipo_deploy = dados.categoria, dados.tipo_deploy
    conn.max_tokens, conn.temperatura = dados.max_tokens, dados.temperatura
    conn.context_window_tokens, conn.rate_limit_rpm = dados.context_window_tokens, dados.rate_limit_rpm
    conn.preco_entrada_por_milhao = dados.preco_entrada_por_milhao
    conn.preco_saida_por_milhao = dados.preco_saida_por_milhao
    conn.moeda = dados.moeda
    if dados.api_key.strip():  # em branco = mantém a atual
        conn.api_key_cifrada = cifrar_ia(dados.api_key)
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


@router.get("/{cid}/revelar")
def revelar(cid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    conn = db.get(AiConnection, cid)
    if not conn:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    return {"api_key": decifrar_ia(conn.api_key_cifrada)}


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
