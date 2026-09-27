"""Guardrail de custo: teto diário/mensal de gasto na IA (US$), protege o orçamento.

Deriva o gasto do `ai_call_log` × preço da API (mesma fonte da telemetria). Imposto
no motor de IA: ao atingir o teto do dia, as chamadas pausam até o dia seguinte."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AiCallLog, AiConnection


def _inicio_dia() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _inicio_mes() -> datetime:
    return datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def gasto_usd(db: Session, desde: datetime) -> float:
    """Gasto real em US$ desde `desde`: tokens (texto/visão/embeddings), segundos
    (transcrição) e caracteres (voz) × preço da API. [170]: antes somava só tokens
    e por isso NÃO enxergava transcrição nem voz — o guardrail via ~metade do
    gasto de uma conversa por voz."""
    from app.modules.ai_registry.precos import precos_da_plataforma
    from app.modules.ai_registry.telemetria import _custo_usd

    rows = db.execute(
        select(
            AiCallLog.connection_id,
            AiCallLog.tipo_unidade,
            func.coalesce(func.sum(AiCallLog.prompt_tokens), 0),
            func.coalesce(func.sum(AiCallLog.completion_tokens), 0),
            func.coalesce(func.sum(AiCallLog.unidades), 0),
        )
        .where(AiCallLog.criado_em >= desde, AiCallLog.connection_id.isnot(None))
        .group_by(AiCallLog.connection_id, AiCallLog.tipo_unidade)
    ).all()
    if not rows:
        return 0.0
    agregado: dict[int, list] = {}
    for cid, tipo, pt, ct, un in rows:
        a = agregado.setdefault(cid, [0, 0, {}])
        a[0] += pt
        a[1] += ct
        if tipo and un:
            a[2][tipo] = a[2].get(tipo, 0) + un
    conns = {c.id: c for c in db.execute(select(AiConnection)).scalars()}
    cache: dict[int, dict] = {}
    total = 0.0
    for cid, (pt, ct, unidades) in agregado.items():
        conn = conns.get(cid)
        if not conn:
            continue
        if conn.platform_id not in cache:
            cache[conn.platform_id] = precos_da_plataforma(conn.plataforma)
        custo, _ = _custo_usd(conn, cache[conn.platform_id], pt, ct, unidades)
        total += custo or 0.0
    return round(total, 6)


def teto_diario(db: Session) -> float:
    from app.core.flags import get_flag

    d = get_flag(db, "orcamento_diario_usd", "")
    if d:
        return float(d)
    return round(float(get_flag(db, "orcamento_mensal_usd", "20")) / 30, 4)


def diario_excedido(db: Session) -> bool:
    teto = teto_diario(db)
    if teto <= 0:
        return False
    return gasto_usd(db, _inicio_dia()) >= teto


def estado(db: Session) -> dict:
    from app.core.flags import get_flag

    mensal = float(get_flag(db, "orcamento_mensal_usd", "20"))
    diario = teto_diario(db)
    hoje = gasto_usd(db, _inicio_dia())
    mes = gasto_usd(db, _inicio_mes())
    now = datetime.now(UTC)
    import calendar

    dias_mes = calendar.monthrange(now.year, now.month)[1]
    projecao = round(mes / now.day * dias_mes, 4) if now.day else 0.0
    return {
        "orcamento_mensal_usd": mensal, "orcamento_diario_usd": diario,
        "gasto_hoje_usd": hoje, "gasto_mes_usd": mes,
        "pct_dia": round(hoje / diario * 100, 1) if diario else 0.0,
        "pct_mes": round(mes / mensal * 100, 1) if mensal else 0.0,
        "projecao_mes_usd": projecao, "diario_excedido": diario > 0 and hoje >= diario,
    }
