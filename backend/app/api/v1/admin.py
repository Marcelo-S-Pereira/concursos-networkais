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
    """Lista de usuários com o saldo de créditos (para o admin doar/ajustar)."""
    us = db.execute(select(User).order_by(User.nome)).scalars().all()
    return [
        {"id": u.id, "nome": u.nome, "email": u.email, "role": u.role,
         "saldo": saldo(db, u.id), "vitalicio": u.vitalicio}
        for u in us
    ]


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
