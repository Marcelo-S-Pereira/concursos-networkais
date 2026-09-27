"""Porta de acesso diária: simulado, chat de estudo e tutor ficam atrás dela.

Abre sozinha no primeiro uso do dia (sem botão "abrir acesso"). Custo do dia =
pool mensal (`pag_creditos_compra`) ÷ dias do mês corrente, arredondado pro
crédito inteiro mais próximo — o app não guarda fração de crédito (o próprio
usuário já aceitou perder o resto no reset mensal; arredondar só muda ONDE a
perda acontece). "A porta está aberta hoje" é derivado, não guardado à parte:
existe uma `CreditTransaction` tipo `acesso_diario` datada de hoje (UTC).

O aluno nunca vê o número bruto do custo diário — só duas barras, no mesmo
padrão visual do plataforma de estudo: **hoje** (contagem regressiva até 23:59:59,
ancorada no momento em que abriu — não na meia-noite, senão quem abre às 23h
veria a barra quase cheia sem ter usado nada) e **semana** (créditos gastos na
semana corrente ÷ alvo semanal = 7 × custo do dia — mesma dupla hoje/semana do
plataforma de estudo de verdade). A semana é só leitura/agregação da mesma
`CreditTransaction` — não existe dedução própria dela; se o aluno não acessa
em algum dia, a barra some naquele dia e reseta na virada da semana, e
"perder" aquele dia é opção do aluno, não bug da plataforma (ele paga o pool
mensal de qualquer forma).
"""

import calendar
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.flags import get_flag
from app.db.models import CreditTransaction, User
from app.modules.creditos.carteira import creditar, saldo

TIPO = "acesso_diario"
POOL_MENSAL_FLAG = "pag_creditos_compra"  # reaproveita o mesmo número da compra mensal


def custo_do_dia(dia: date, pool_mensal: int) -> int:
    dias_no_mes = calendar.monthrange(dia.year, dia.month)[1]
    return max(1, round(pool_mensal / dias_no_mes))


def _isento(user: User) -> bool:
    """Superadmin e vitalício ([169]: regra única em `User.sem_limites`).
    "Moderador" não é um papel que existe no sistema ainda — não invento um aqui."""
    return user.sem_limites


def ja_pago_hoje(db: Session, user_id: int, hoje: date | None = None) -> bool:
    hoje = hoje or datetime.now(UTC).date()
    linhas = db.execute(
        select(CreditTransaction.criado_em).where(
            CreditTransaction.user_id == user_id, CreditTransaction.tipo == TIPO,
        )
    ).scalars()
    return any(c and c.date() == hoje for c in linhas)


def abrir(db: Session, user: User) -> str | None:
    """Garante a porta aberta hoje para este usuário. Devolve None se já está
    aberta (ou é isento); devolve a mensagem de erro se não há crédito — quem
    chama decide o HTTP (mesmo idioma de `limites.bloqueio`)."""
    if _isento(user):
        return None
    hoje = datetime.now(UTC).date()
    if ja_pago_hoje(db, user.id, hoje):
        return None
    pool = int(get_flag(db, POOL_MENSAL_FLAG, "155"))
    custo = custo_do_dia(hoje, pool)
    if saldo(db, user.id) < custo:
        return "Créditos insuficientes para abrir o acesso de hoje. Compre créditos no seu perfil."
    creditar(db, user.id, -custo, TIPO, f"acesso do dia {hoje.isoformat()}")
    return None


def estado_hoje(db: Session, user: User) -> dict:
    """Pro front montar a barra de contagem regressiva: quando abriu (se já
    abriu) e quando fecha (23:59:59 de hoje, UTC) — o front tica o relógio
    sozinho a partir daqui, mesmo padrão do cronômetro do simulado."""
    if _isento(user):
        return {"isento": True, "aberto": False, "abriu_em": None, "fecha_em": None}
    hoje = datetime.now(UTC).date()
    fecha_em = datetime.combine(hoje, datetime.max.time(), UTC)
    linha = db.execute(
        select(CreditTransaction.criado_em).where(
            CreditTransaction.user_id == user.id, CreditTransaction.tipo == TIPO,
        ).order_by(CreditTransaction.criado_em.desc())
    ).scalars().first()
    abriu_hoje = linha if linha and linha.date() == hoje else None
    return {
        "isento": False, "aberto": abriu_hoje is not None,
        "abriu_em": abriu_hoje.isoformat() if abriu_hoje else None,
        "fecha_em": fecha_em.isoformat(),
    }


def resumo_semana(db: Session, user: User) -> dict:
    """Créditos gastos na semana corrente (segunda a domingo, UTC) ÷ alvo
    semanal (7 × custo do dia de hoje). Pura leitura/agregação da mesma
    `CreditTransaction` que a porta diária já grava — sem dedução própria."""
    if _isento(user):
        return {"isento": True, "usado": 0, "alvo": 0}
    hoje = datetime.now(UTC).date()
    inicio_semana_dia = hoje - timedelta(days=hoje.weekday())  # segunda-feira
    inicio_semana = datetime.combine(inicio_semana_dia, datetime.min.time(), UTC)
    linhas = db.execute(
        select(CreditTransaction.delta).where(
            CreditTransaction.user_id == user.id, CreditTransaction.tipo == TIPO,
            CreditTransaction.criado_em >= inicio_semana,
        )
    ).scalars()
    usado = -sum(linhas)
    pool = int(get_flag(db, POOL_MENSAL_FLAG, "155"))
    alvo = 7 * custo_do_dia(hoje, pool)
    return {"isento": False, "usado": usado, "alvo": alvo}
