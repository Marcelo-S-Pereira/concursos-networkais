"""Catálogo de plataformas e modelos, carregado do banco (nada chumbado no
front/back). O front lê as listas daqui; o admin edita e sincroniza do provedor."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import apenas_superadmin
from app.db.models import AiPlatform, CatalogModel, CatalogPlatform, User
from app.db.session import get_db

router = APIRouter(prefix="/ai/catalogo")

# mapeia o "type" do /models do provedor para a nossa categoria
TIPO_CATEGORIA = {
    "chat": "texto", "language": "texto", "code": "texto",
    "embedding": "embeddings", "embeddings": "embeddings",
    "image": "visao", "vision": "visao",
    "audio": "transcricao", "transcribe": "transcricao", "stt": "transcricao",
    "tts": "voz", "speech": "voz",
}


class PlatOut(BaseModel):
    nome: str
    endpoint: str


class ModeloOut(BaseModel):
    id: int
    model_id: str
    rotulo: str
    dim: int | None
    padrao: bool


@router.get("/plataformas", response_model=list[PlatOut])
def plataformas(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    return [PlatOut(nome=p.nome, endpoint=p.endpoint)
            for p in db.execute(select(CatalogPlatform).order_by(CatalogPlatform.nome)).scalars()]


@router.get("/modelos", response_model=list[ModeloOut])
def modelos(plataforma: str, categoria: str, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    q = db.execute(
        select(CatalogModel).where(CatalogModel.plataforma == plataforma, CatalogModel.categoria == categoria)
        .order_by(CatalogModel.padrao.desc(), CatalogModel.model_id)
    ).scalars()
    return [ModeloOut(id=m.id, model_id=m.model_id, rotulo=m.rotulo, dim=m.dim, padrao=m.padrao) for m in q]


class ModeloIn(BaseModel):
    plataforma: str
    categoria: str
    model_id: str
    rotulo: str = ""
    dim: int | None = None
    padrao: bool = False


@router.post("/modelos", response_model=ModeloOut, status_code=201)
def add_modelo(dados: ModeloIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    existe = db.execute(select(CatalogModel).where(
        CatalogModel.plataforma == dados.plataforma, CatalogModel.categoria == dados.categoria,
        CatalogModel.model_id == dados.model_id)).scalar_one_or_none()
    if existe:
        raise HTTPException(status_code=409, detail="Modelo já está no catálogo.")
    m = CatalogModel(**dados.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return ModeloOut(id=m.id, model_id=m.model_id, rotulo=m.rotulo, dim=m.dim, padrao=m.padrao)


@router.delete("/modelos/{mid}", status_code=204)
def del_modelo(mid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    m = db.get(CatalogModel, mid)
    if m:
        db.delete(m)
        db.commit()


@router.post("/sincronizar/{platform_id}")
def sincronizar(platform_id: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Chama GET {endpoint}/models do provedor cadastrado e popula o catálogo com
    os modelos reais, categorizados pelo campo `type` quando disponível."""
    import httpx

    from app.core.crypto import decifrar_ia

    plat = db.get(AiPlatform, platform_id)
    if not plat:
        raise HTTPException(status_code=404, detail="Plataforma não encontrada.")

    # nome do catálogo: casa pelo endpoint, senão usa o título
    cat = db.execute(select(CatalogPlatform).where(CatalogPlatform.endpoint == plat.endpoint)).scalar_one_or_none()
    nome = cat.nome if cat else plat.titulo

    chave = decifrar_ia(plat.api_key_cifrada)
    headers = {"Authorization": f"Bearer {chave}"} if chave else {}
    try:
        resp = httpx.get(plat.endpoint.rstrip("/") + "/models", headers=headers, timeout=30)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Falha ao consultar o provedor: {e}") from e
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Provedor respondeu {resp.status_code}: {resp.text[:200]}")

    dados = resp.json()
    itens = dados.get("data") if isinstance(dados, dict) else dados
    if not isinstance(itens, list):
        raise HTTPException(status_code=502, detail="Formato inesperado do /models do provedor.")

    novos = 0
    for it in itens:
        model_id = (it.get("id") or "").strip() if isinstance(it, dict) else str(it)
        if not model_id:
            continue
        tipo = str(it.get("type") or "").lower() if isinstance(it, dict) else ""
        categoria = TIPO_CATEGORIA.get(tipo, "texto")
        existe = db.execute(select(CatalogModel).where(
            CatalogModel.plataforma == nome, CatalogModel.categoria == categoria,
            CatalogModel.model_id == model_id)).scalar_one_or_none()
        if not existe:
            db.add(CatalogModel(plataforma=nome, categoria=categoria, model_id=model_id, rotulo="do provedor"))
            novos += 1
    db.commit()
    return {"plataforma": nome, "modelos_no_provedor": len(itens), "novos_no_catalogo": novos}
