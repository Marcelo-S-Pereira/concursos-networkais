"""Carteira de créditos do próprio usuário (saldo, ganho, gasto, extrato)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import usuario_atual
from app.db.models import User
from app.db.session import get_db
from app.modules.creditos.carteira import resumo

router = APIRouter(prefix="/creditos")


@router.get("")
def meus_creditos(user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    r = resumo(db, user.id)
    # acesso livre (não consome crédito): o dono OU quem tem vitalício. Decidido no
    # servidor a partir do banco — o cliente não influencia isto.
    r["acesso_livre"] = user.role == "superadmin" or user.vitalicio
    r["vitalicio"] = user.vitalicio
    return r
