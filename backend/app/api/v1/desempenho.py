"""Desempenho consolidado do usuário (Mastery, dificuldade, macete, gamificação).

Só leitura, derivado dos dados persistidos. Autenticado (cada um vê o seu)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import usuario_atual
from app.db.models import User
from app.db.session import get_db
from app.modules.desempenho.consolidado import (
    dificuldade_por_enfase,
    eficacia_macete,
    gamificacao,
    mastery_consolidado,
)

router = APIRouter(prefix="/desempenho")


@router.get("")
def resumo(user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    return {
        "mastery": mastery_consolidado(db, user.id),
        "dificuldade": dificuldade_por_enfase(db, user.id),
        "macete": eficacia_macete(db, user.id),
        "gamificacao": gamificacao(db, user.id),
    }
