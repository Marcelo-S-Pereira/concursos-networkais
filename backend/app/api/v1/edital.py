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


class RegrasOut(RegrasIn):
    exam_id: int


@router.get("/{exam_id}/regras", response_model=RegrasOut | None)
def obter_regras(exam_id: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    r = db.execute(select(ExamRules).where(ExamRules.exam_id == exam_id)).scalar_one_or_none()
    if not r:
        return None
    return RegrasOut(exam_id=exam_id, pesos=r.pesos, minimos=r.minimos, nota_corte=r.nota_corte, vagas=r.vagas)


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
    db.commit()
    return RegrasOut(exam_id=exam_id, pesos=r.pesos, minimos=r.minimos, nota_corte=r.nota_corte, vagas=r.vagas)
