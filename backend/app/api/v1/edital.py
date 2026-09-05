"""Regras do edital por caderno (spec §7.1). CRUD admin — o usuário preenche as
regras (ou o parser do edital preenche, quando houver PDF)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import apenas_superadmin
from app.db.models import Exam, ExamRules, User
from app.db.session import get_db

router = APIRouter(prefix="/exames")


class RegrasIn(BaseModel):
    pesos: dict[str, float] = {}
    minimos: dict[str, int] = {}
    nota_corte: float | None = None
    vagas: int | None = None
    fases: dict[str, str] = {}
    minimo_pct_fase: dict[str, float] = {}
    materias_sem_zero: list[str] = []


class RegrasOut(RegrasIn):
    exam_id: int


@router.get("/{exam_id}/regras", response_model=RegrasOut | None)
def obter_regras(exam_id: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    r = db.execute(select(ExamRules).where(ExamRules.exam_id == exam_id)).scalar_one_or_none()
    if not r:
        return None
    return RegrasOut(exam_id=exam_id, pesos=r.pesos, minimos=r.minimos, nota_corte=r.nota_corte,
                     vagas=r.vagas, fases=r.fases, minimo_pct_fase=r.minimo_pct_fase,
                     materias_sem_zero=r.materias_sem_zero)


@router.put("/{exam_id}/regras", response_model=RegrasOut)
def gravar_regras(exam_id: int, dados: RegrasIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    if not db.get(Exam, exam_id):
        raise HTTPException(status_code=404, detail="Prova não encontrada.")
    r = db.execute(select(ExamRules).where(ExamRules.exam_id == exam_id)).scalar_one_or_none()
    if not r:
        r = ExamRules(exam_id=exam_id)
        db.add(r)
    r.pesos = dados.pesos
    r.minimos = dados.minimos
    r.nota_corte = dados.nota_corte
    r.vagas = dados.vagas
    r.fases = dados.fases
    r.minimo_pct_fase = dados.minimo_pct_fase
    r.materias_sem_zero = dados.materias_sem_zero
    db.commit()
    return RegrasOut(exam_id=exam_id, pesos=r.pesos, minimos=r.minimos, nota_corte=r.nota_corte,
                     vagas=r.vagas, fases=r.fases, minimo_pct_fase=r.minimo_pct_fase,
                     materias_sem_zero=r.materias_sem_zero)
