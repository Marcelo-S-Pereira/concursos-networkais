"""Limites rolantes de uso de IA por usuário, no modelo do plataforma de estudo.

Duas janelas:

- **Sessão de 5h** — começa na PRIMEIRA mensagem e expira 5h depois; a mensagem
  seguinte abre uma janela nova. Não é uma janela deslizante: é um bloco fixo
  ancorado no primeiro uso, igual ao plataforma de estudo. Calculado sem estado extra,
  varrendo os carimbos das chamadas do usuário.
- **Semana rolante de 7 dias** — a vaga volta quando a chamada mais antiga sai
  da janela.

A unidade é **mensagem** (chamada de IA), não token: é o que o aluno entende e
consegue prever. O lado do dinheiro é do guardrail de orçamento (`orcamento.py`),
que é em US$. Divisão de responsabilidade: limite rolante = ritmo justo por
pessoa; orçamento = proteção do bolso.

Conta TODAS as chamadas de IA do usuário (chat, tutor, gêmeas…), não só o chat —
é o consumo real, e contar só o chat deixaria furo pelos outros endpoints.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.flags import get_flag
from app.db.models import AiCallLog

JANELA_SESSAO_H = 5
JANELA_SEMANA_D = 7
SESSAO = timedelta(hours=JANELA_SESSAO_H)
SEMANA = timedelta(days=JANELA_SEMANA_D)

PADRAO_SESSAO = "40"
PADRAO_SEMANA = "200"


def _int_flag(db: Session, chave: str, padrao: str) -> int:
    """0 (ou vazio/inválido) = sem limite."""
    try:
        return max(0, int(get_flag(db, chave, padrao) or 0))
    except ValueError:
        return 0


def limites_configurados(db: Session) -> dict:
    return {
        "sessao_msgs": _int_flag(db, "limite_sessao_msgs", PADRAO_SESSAO),
        "semana_msgs": _int_flag(db, "limite_semana_msgs", PADRAO_SEMANA),
        "janela_sessao_h": JANELA_SESSAO_H,
        "janela_semana_d": JANELA_SEMANA_D,
    }


def _carimbos(db: Session, user_id: int, desde: datetime) -> list[datetime]:
    return [
        t if t.tzinfo else t.replace(tzinfo=UTC)
        for t in db.execute(
            select(AiCallLog.criado_em)
            .where(AiCallLog.user_id == user_id, AiCallLog.criado_em >= desde)
            .order_by(AiCallLog.criado_em)
        ).scalars()
    ]


def _sessao_vigente(carimbos: list[datetime], agora: datetime) -> tuple[datetime | None, int]:
    """Âncora da sessão viva e quantas chamadas ela já tem.

    Devolve (None, 0) quando não há sessão aberta — aí a próxima mensagem abre uma.
    """
    ancora: datetime | None = None
    n = 0
    for t in carimbos:
        if ancora is None or t >= ancora + SESSAO:
            ancora, n = t, 1
        else:
            n += 1
    if ancora is None or agora >= ancora + SESSAO:
        return None, 0
    return ancora, n


def _quando_libera_semana(carimbos: list[datetime], limite: int) -> datetime | None:
    """Quando a semana volta a ter vaga: a chamada que precisa envelhecer sai da janela."""
    if not carimbos or not limite:
        return None
    i = max(0, len(carimbos) - limite)
    return carimbos[i] + SEMANA


def estado(db: Session, user_id: int, *, isento: bool = False) -> dict:
    agora = datetime.now(UTC)
    lim_s = _int_flag(db, "limite_sessao_msgs", PADRAO_SESSAO)
    lim_w = _int_flag(db, "limite_semana_msgs", PADRAO_SEMANA)
    carimbos = _carimbos(db, user_id, agora - SEMANA)

    ancora, usadas_s = _sessao_vigente(carimbos, agora)
    usadas_w = len(carimbos)

    return {
        "isento": isento,
        "janela_sessao_h": JANELA_SESSAO_H,
        "janela_semana_d": JANELA_SEMANA_D,
        "sessao": {
            "usadas": usadas_s,
            "limite": lim_s,
            "restam": max(0, lim_s - usadas_s) if lim_s else None,
            "reinicia_em": (ancora + SESSAO).isoformat() if ancora else None,
        },
        "semana": {
            "usadas": usadas_w,
            "limite": lim_w,
            "restam": max(0, lim_w - usadas_w) if lim_w else None,
            "libera_em": (
                d.isoformat() if (d := _quando_libera_semana(carimbos, lim_w)) else None
            ),
        },
        "bloqueado": bool(motivo_bloqueio(lim_s, usadas_s, ancora, lim_w, usadas_w, carimbos)) and not isento,
    }


def _hora_local(quando: datetime | None) -> str:
    if not quando:
        return "em breve"
    try:
        from zoneinfo import ZoneInfo

        local = quando.astimezone(ZoneInfo("America/Sao_Paulo"))
        return local.strftime("%d/%m às %H:%M")
    except Exception:  # noqa: BLE001 - sem tzdata, mostra em UTC em vez de quebrar
        return quando.strftime("%d/%m às %H:%M UTC")


def motivo_bloqueio(
    lim_s: int, usadas_s: int, ancora: datetime | None,
    lim_w: int, usadas_w: int, carimbos: list[datetime],
) -> str | None:
    if lim_s and usadas_s >= lim_s:
        volta = _hora_local(ancora + SESSAO if ancora else None)
        return (
            f"Limite da sessão de {JANELA_SESSAO_H}h atingido "
            f"({usadas_s}/{lim_s} mensagens). A sessão reinicia {volta}."
        )
    if lim_w and usadas_w >= lim_w:
        volta = _hora_local(_quando_libera_semana(carimbos, lim_w))
        return (
            f"Limite semanal atingido ({usadas_w}/{lim_w} mensagens em "
            f"{JANELA_SEMANA_D} dias). Libera {volta}."
        )
    return None


def bloqueio(db: Session, user_id: int, *, isento: bool = False) -> str | None:
    """Mensagem explicando o bloqueio, ou None se pode usar."""
    if isento:
        return None
    agora = datetime.now(UTC)
    lim_s = _int_flag(db, "limite_sessao_msgs", PADRAO_SESSAO)
    lim_w = _int_flag(db, "limite_semana_msgs", PADRAO_SEMANA)
    carimbos = _carimbos(db, user_id, agora - SEMANA)
    ancora, usadas_s = _sessao_vigente(carimbos, agora)
    return motivo_bloqueio(lim_s, usadas_s, ancora, lim_w, len(carimbos), carimbos)
