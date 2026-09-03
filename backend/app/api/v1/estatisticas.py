"""Estatística pública por ênfase (spec §9): CRUD admin para o usuário preencher
os dados (scraping/manual). Sem inventar — quando não há dado, status marca."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import apenas_superadmin
from app.db.models import EmphasisPublicStat, User
from app.db.session import get_db

router = APIRouter(prefix="/estatisticas/enfase")


class StatIn(BaseModel):
    banca: str = ""
    orgao: str = ""
    cargo: str = ""
    ano: int | None = None
    enfase: str
    amostra: int | None = None
    acerto_pct: float | None = None
    fonte: str = ""
    tipo_fonte: str = ""
    status: str = "OK"


class StatOut(StatIn):
    id: int


def _saida(x: EmphasisPublicStat) -> StatOut:
    return StatOut(
        id=x.id, banca=x.banca, orgao=x.orgao, cargo=x.cargo, ano=x.ano, enfase=x.enfase,
        amostra=x.amostra, acerto_pct=x.acerto_pct, fonte=x.fonte, tipo_fonte=x.tipo_fonte, status=x.status,
    )


@router.get("", response_model=list[StatOut])
def listar(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    return [_saida(x) for x in db.execute(select(EmphasisPublicStat).order_by(EmphasisPublicStat.enfase)).scalars()]


@router.post("", response_model=StatOut, status_code=201)
def criar(dados: StatIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    x = EmphasisPublicStat(**dados.model_dump())
    db.add(x)
    db.commit()
    db.refresh(x)
    return _saida(x)


@router.patch("/{sid}", response_model=StatOut)
def editar(sid: int, dados: StatIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    x = db.get(EmphasisPublicStat, sid)
    if not x:
        raise HTTPException(status_code=404, detail="Estatística não encontrada.")
    for campo, valor in dados.model_dump().items():
        setattr(x, campo, valor)
    db.commit()
    db.refresh(x)
    return _saida(x)


@router.delete("/{sid}", status_code=204)
def apagar(sid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    x = db.get(EmphasisPublicStat, sid)
    if x:
        db.delete(x)
        db.commit()
