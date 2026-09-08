"""Flags/configurações simples do sistema (tabela system_settings)."""

from sqlalchemy.orm import Session

from app.db.models import SystemSetting

CADASTROS_BLOQUEADOS = "cadastros_bloqueados"


def get_flag(db: Session, chave: str, padrao: str = "") -> str:
    row = db.get(SystemSetting, chave)
    return row.valor if row else padrao


def set_flag(db: Session, chave: str, valor: str) -> None:
    row = db.get(SystemSetting, chave)
    if row:
        row.valor = valor
    else:
        db.add(SystemSetting(chave=chave, valor=valor))
    db.commit()


def cadastros_bloqueados(db: Session) -> bool:
    return get_flag(db, CADASTROS_BLOQUEADOS, "0") == "1"
