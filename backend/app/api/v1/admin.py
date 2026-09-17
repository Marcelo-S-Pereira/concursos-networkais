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
from app.db.models import CreditTransaction, Exam, Question, SimulationRun, User
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


@router.get("/fila")
def fila_estado(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """[126]: config + retrato ao vivo (em voo/esperando/CPU/memória/disco)."""
    from app.modules.ai_registry.fila import estado
    return estado(db)


class FilaIn(BaseModel):
    max_concorrente: int
    cpu_pct_max: float
    mem_pct_max: float
    disco_pct_max: float
    timeout_espera_s: float


@router.post("/fila")
def salvar_fila(dados: FilaIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    from app.modules.ai_registry.fila import estado, salvar_config
    salvar_config(
        db, max_concorrente=dados.max_concorrente, cpu_pct_max=dados.cpu_pct_max,
        mem_pct_max=dados.mem_pct_max, disco_pct_max=dados.disco_pct_max,
        timeout_espera_s=dados.timeout_espera_s,
    )
    return estado(db)


@router.get("/fila/historico")
def fila_historico(dias: int = 7, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """[126]: amostras persistidas (a cada 3 min, pelo monitor de fundo) —
    para decidir quando escalar a partir de tendência, não só do instante."""
    from datetime import UTC, datetime, timedelta

    from app.db.models import FilaHistorico

    desde = datetime.now(UTC) - timedelta(days=max(1, min(dias, 90)))
    linhas = db.execute(
        select(FilaHistorico).where(FilaHistorico.criado_em >= desde).order_by(FilaHistorico.criado_em)
    ).scalars().all()
    return [
        {
            "quando": r.criado_em.isoformat(), "cpu_pct": r.cpu_pct, "memoria_pct": r.memoria_pct,
            "disco_pct": r.disco_pct, "em_voo": r.em_voo, "esperando": r.esperando,
            "max_concorrente": r.max_concorrente, "admitidas": r.admitidas, "rejeitadas": r.rejeitadas,
            "espera_media_ms": r.espera_media_ms,
        }
        for r in linhas
    ]


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
    ranking: falta indicação/referência, que ainda não existe no app.

    Exclui o próprio superadmin ([104]) — ele é sempre `acesso_livre`, então
    doar crédito ou alternar vitalício pra si mesmo não faz efeito nenhum
    (nem aparece em lugar nenhum da tela dele), e listá-lo aqui só abre
    espaço pro admin clicar em si mesmo por engano em vez do usuário certo.

    `mesmo_cpf_dono` ([105]): compara só o `cpf_indice` (hash determinístico,
    [013]) — o CPF em si nunca sai desta rota. `comprado`/`doado` somam o
    ledger por tipo (compra vs bonus/ajuste) — hoje `comprado` é sempre 0
    porque o checkout do Mercado Pago ([075]) nunca foi concluído."""
    from app.modules.features.features import grants_do_usuario

    dono = db.execute(select(User).where(User.role == "superadmin")).scalar_one_or_none()
    cpf_dono = dono.cpf_indice if dono else None
    us = db.execute(select(User).where(User.role != "superadmin").order_by(User.nome)).scalars().all()
    linhas = []
    for u in us:
        simulados = db.scalar(
            select(func.count()).select_from(SimulationRun)
            .where(SimulationRun.user_id == u.id, SimulationRun.status == "finished")
        ) or 0
        comprado = db.scalar(
            select(func.coalesce(func.sum(CreditTransaction.delta), 0))
            .where(CreditTransaction.user_id == u.id, CreditTransaction.tipo == "compra")
        ) or 0
        doado = db.scalar(
            select(func.coalesce(func.sum(CreditTransaction.delta), 0))
            .where(CreditTransaction.user_id == u.id, CreditTransaction.tipo.in_(("bonus", "ajuste")),
                   CreditTransaction.delta > 0)
        ) or 0
        linhas.append({
            "id": u.id, "nome": u.nome, "email": u.email, "role": u.role,
            "saldo": saldo(db, u.id), "vitalicio": u.vitalicio,
            "simulados": simulados, "recursos": grants_do_usuario(db, u.id),
            "mesmo_cpf_dono": bool(cpf_dono) and u.cpf_indice == cpf_dono,
            "comprado": comprado, "doado": doado,
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
