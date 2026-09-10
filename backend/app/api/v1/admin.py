"""Painel do administrador (só superadmin): visão geral de uso.

Números reais derivados dos dados. Créditos/planos e sistema de Ad ainda não
existem (dependem do módulo de pagamentos) — não são retornados aqui."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import apenas_superadmin
from app.core.flags import cadastros_bloqueados, set_flag
from app.core.saude import medir
from app.db.models import Exam, Question, SimulationRun, User
from app.db.session import get_db
from app.modules.creditos.carteira import creditar, creditar_lote, saldo

router = APIRouter(prefix="/admin")


@router.get("/overview")
def overview(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    return {
        "usuarios": db.scalar(select(func.count()).select_from(User)) or 0,
        "simulados_feitos": db.scalar(
            select(func.count()).select_from(SimulationRun).where(SimulationRun.status == "finished")
        ) or 0,
        "cadernos": db.scalar(
            select(func.count()).select_from(Exam).where(Exam.excluido_em.is_(None))
        ) or 0,
        "questoes": db.scalar(select(func.count()).select_from(Question)) or 0,
    }


@router.get("/orcamento")
def orcamento(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    from app.modules.ai_registry.orcamento import estado
    return estado(db)


class OrcamentoIn(BaseModel):
    mensal_usd: float
    diario_usd: float | None = None


@router.post("/orcamento")
def salvar_orcamento(dados: OrcamentoIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    from app.modules.ai_registry.orcamento import estado
    set_flag(db, "orcamento_mensal_usd", str(dados.mensal_usd))
    set_flag(db, "orcamento_diario_usd", str(dados.diario_usd) if dados.diario_usd else "")
    return estado(db)


@router.get("/limites")
def limites_uso(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Tetos rolantes de uso de IA por usuário (sessão de 5h e semana de 7 dias)."""
    from app.modules.ai_registry.limites import limites_configurados
    return limites_configurados(db)


class LimitesIn(BaseModel):
    sessao_msgs: int
    semana_msgs: int


@router.post("/limites")
def salvar_limites(dados: LimitesIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    from app.modules.ai_registry.limites import limites_configurados
    set_flag(db, "limite_sessao_msgs", str(max(0, dados.sessao_msgs)))
    set_flag(db, "limite_semana_msgs", str(max(0, dados.semana_msgs)))
    return limites_configurados(db)


@router.get("/youtube")
def youtube_config(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Estado da chave da YouTube Data API — nunca em claro, só mascarada."""
    from app.modules.youtube.youtube import chave_mascarada, configurada
    return {"configurada": configurada(db), "chave_mascarada": chave_mascarada(db)}


class YoutubeIn(BaseModel):
    chave: str


@router.put("/youtube")
def salvar_youtube(dados: YoutubeIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    from app.modules.youtube.youtube import chave_mascarada, salvar_chave
    if not dados.chave.strip():
        raise HTTPException(status_code=422, detail="Informe a chave da API.")
    salvar_chave(db, dados.chave)
    return {"configurada": True, "chave_mascarada": chave_mascarada(db)}


@router.delete("/youtube", status_code=204)
def apagar_youtube(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    from app.modules.youtube.youtube import apagar_chave
    apagar_chave(db)


@router.post("/youtube/testar")
def testar_youtube(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    from app.modules.youtube.youtube import testar
    return testar(db)


@router.get("/saude")
def saude(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Saúde da ambiente de execucao (carga/memória/disco/conexões) + se cadastros estão bloqueados."""
    return {**medir(db), "cadastros_bloqueados": cadastros_bloqueados(db)}


class BloqueioIn(BaseModel):
    bloqueado: bool


@router.post("/cadastros")
def alternar_cadastros(dados: BloqueioIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Liga/desliga o bloqueio de novos cadastros (para proteger a ambiente de execucao)."""
    from app.core.flags import CADASTROS_BLOQUEADOS
    set_flag(db, CADASTROS_BLOQUEADOS, "1" if dados.bloqueado else "0")
    return {"cadastros_bloqueados": dados.bloqueado}


@router.get("/usuarios")
def usuarios(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Lista de usuários com saldo, vitalício e recursos restritos concedidos —
    ordenada por quem mais usa (simulados feitos) primeiro. É o começo do
    ranking: falta indicação/referência, que ainda não existe no app."""
    from app.modules.features.features import grants_do_usuario

    us = db.execute(select(User).order_by(User.nome)).scalars().all()
    linhas = []
    for u in us:
        simulados = db.scalar(
            select(func.count()).select_from(SimulationRun)
            .where(SimulationRun.user_id == u.id, SimulationRun.status == "finished")
        ) or 0
        linhas.append({
            "id": u.id, "nome": u.nome, "email": u.email, "role": u.role,
            "saldo": saldo(db, u.id), "vitalicio": u.vitalicio,
            "simulados": simulados, "recursos": grants_do_usuario(db, u.id),
        })
    linhas.sort(key=lambda x: x["simulados"], reverse=True)
    return linhas


@router.get("/recursos/catalogo")
def recursos_catalogo(_: User = Depends(apenas_superadmin)):
    from app.modules.features.features import RECURSOS
    return RECURSOS


class ConcederRecursoIn(BaseModel):
    email: str
    feature: str
    limite_diario: int = 5


@router.post("/recursos/conceder")
def conceder_recurso(dados: ConcederRecursoIn, admin: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Libera um recurso restrito para um usuário, com o teto de uso por dia
    que o admin escolhe — o resto da comunidade continua sem acesso."""
    from app.modules.features.features import RECURSOS, conceder

    if dados.feature not in RECURSOS:
        raise HTTPException(status_code=422, detail="Recurso inválido.")
    u = db.execute(select(User).where(User.email == dados.email.strip().lower())).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    conceder(db, u.id, dados.feature, dados.limite_diario, admin.id)
    return {"ok": True}


class RevogarRecursoIn(BaseModel):
    email: str
    feature: str


@router.post("/recursos/revogar")
def revogar_recurso(dados: RevogarRecursoIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    from app.modules.features.features import revogar

    u = db.execute(select(User).where(User.email == dados.email.strip().lower())).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    revogar(db, u.id, dados.feature)
    return {"ok": True}


@router.get("/youtube/uso")
def youtube_uso(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Consumo real do pool do YouTube hoje — inclui o uso do próprio admin,
    porque é a cota de verdade do Google sendo gasta, não só a da comunidade."""
    from app.modules.features.features import RECURSOS, uso_total_hoje

    buscas = uso_total_hoje(db, "youtube_videos")
    custo = RECURSOS["youtube_videos"]["custo_unidade_api"]
    unidades = buscas * custo
    cota = 10_000
    return {
        "buscas_hoje": buscas, "unidades_hoje": unidades, "cota_diaria_unidades": cota,
        "pct": round(unidades / cota * 100, 1) if cota else 0.0,
    }


class VitalicioIn(BaseModel):
    email: str
    vitalicio: bool


@router.post("/vitalicio")
def definir_vitalicio(dados: VitalicioIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Liga/desliga o acesso vitalício de um usuário (não consome créditos).
    Só o superadmin, no servidor — o cliente nunca altera isso."""
    u = db.execute(select(User).where(User.email == dados.email.strip().lower())).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    u.vitalicio = dados.vitalicio
    db.commit()
    return {"email": u.email, "vitalicio": u.vitalicio}


class CreditarIn(BaseModel):
    email: str
    creditos: int
    motivo: str = ""


@router.post("/creditar")
def creditar_usuario(dados: CreditarIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """O dono concede/ajusta crédito de um usuário (cortesia ou teste)."""
    u = db.execute(select(User).where(User.email == dados.email.strip().lower())).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    creditar(db, u.id, dados.creditos, "ajuste", dados.motivo or "ajuste do admin")
    return {"ok": True, "saldo": saldo(db, u.id)}


ALVOS = {"todos", "mais_ativos", "primeiros"}


def _alvos_campanha(db: Session, alvo: str, limite: int) -> list[User]:
    base = select(User).where(User.role != "superadmin")  # o dono é livre, fora das campanhas
    if alvo == "todos":
        return list(db.execute(base).scalars())
    if alvo == "primeiros":
        return list(db.execute(base.order_by(User.created_at).limit(max(1, limite))).scalars())
    if alvo == "mais_ativos":
        sub = (
            select(SimulationRun.user_id, func.count().label("n"))
            .where(SimulationRun.status == "finished")
            .group_by(SimulationRun.user_id)
            .subquery()
        )
        q = (
            select(User).where(User.role != "superadmin")
            .join(sub, sub.c.user_id == User.id)
            .order_by(sub.c.n.desc()).limit(max(1, limite))
        )
        return list(db.execute(q).scalars())
    return []


@router.get("/campanha/previa")
def campanha_previa(alvo: str, limite: int = 100, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    if alvo not in ALVOS:
        raise HTTPException(status_code=422, detail="Alvo inválido.")
    us = _alvos_campanha(db, alvo, limite)
    return {"quantos": len(us), "exemplos": [u.nome for u in us[:5]]}


class CampanhaIn(BaseModel):
    alvo: str
    quantidade: int
    motivo: str = ""
    limite: int = 100


@router.post("/campanha")
def campanha(dados: CampanhaIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    if dados.alvo not in ALVOS:
        raise HTTPException(status_code=422, detail="Alvo inválido.")
    if dados.quantidade == 0:
        raise HTTPException(status_code=422, detail="Informe a quantidade de créditos.")
    us = _alvos_campanha(db, dados.alvo, dados.limite)
    n = creditar_lote(db, [u.id for u in us], dados.quantidade, "bonus", dados.motivo or f"campanha: {dados.alvo}")
    return {"beneficiados": n}
