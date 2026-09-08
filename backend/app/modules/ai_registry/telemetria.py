"""Telemetria de uso por modelo (conexão), derivada na leitura.

Uso (requisições, erros, tokens, tempo, unidades) vem do `ai_call_log` — que grava
cada chamada. Preço vem do PROVEDOR (precos.py, API), nunca digitado. Custo =
uso × preço; convertido a BRL pela cotação. Também deriva o gasto por hora e por
minuto (custo ÷ tempo de uso). Nada é gravado em duplicidade (v4.1 §1.2).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AiCallLog, AiConnection
from app.modules.ai_registry.cotacao import usd_brl
from app.modules.ai_registry.precos import precos_da_plataforma


def _custo_usd(conn, precos: dict, pt: int, ct: int, unidades: dict[str, int]) -> tuple[float | None, dict | None]:
    """Custo em USD pela categoria + preço da API. Devolve (custo, preco_usado)."""
    p = precos.get((conn.modelo or "").lower())
    if not p:
        return None, None
    cat = conn.categoria
    if cat == "transcricao" and p.get("por_minuto"):
        segundos = sum(unidades.values()) if unidades else 0
        return segundos / 60 * p["por_minuto"], p
    if cat == "voz":
        chars = sum(unidades.values()) if unidades else 0
        return chars / 1e6 * p["input"], p
    # texto | visao | embeddings: por tokens
    return pt / 1e6 * p["input"] + ct / 1e6 * p["output"], p


def resumo_por_conexao(db: Session) -> dict:
    taxa, fonte = usd_brl()
    conns = list(db.execute(select(AiConnection)).scalars())

    # busca o preço de cada plataforma uma vez só (cache interno por plataforma)
    precos_por_plat: dict[int, dict] = {}

    por_conexao = []
    for conn in conns:
        if conn.platform_id not in precos_por_plat:
            precos_por_plat[conn.platform_id] = precos_da_plataforma(conn.plataforma)
        precos = precos_por_plat[conn.platform_id]

        logs = list(
            db.execute(
                select(AiCallLog)
                .where(AiCallLog.connection_id == conn.id)
                .order_by(AiCallLog.criado_em.desc())
            ).scalars()
        )
        erros = [x for x in logs if not x.sucesso]
        pt = sum(x.prompt_tokens or 0 for x in logs)
        ct = sum(x.completion_tokens or 0 for x in logs)
        tt = sum((x.total_tokens or (x.prompt_tokens or 0) + (x.completion_tokens or 0)) for x in logs)
        seg = sum(x.latencia_ms or 0 for x in logs) / 1000.0

        unidades: dict[str, int] = {}
        for x in logs:
            if x.unidades and x.tipo_unidade:
                unidades[x.tipo_unidade] = unidades.get(x.tipo_unidade, 0) + x.unidades

        custo_usd, p = _custo_usd(conn, precos, pt, ct, unidades)
        custo_brl = custo_usd * taxa if custo_usd is not None else None

        # taxa de gasto (custo ÷ tempo de uso) e projeção a esse ritmo
        horas = seg / 3600
        minutos = seg / 60
        gasto_hora_usd = custo_usd / horas if custo_usd is not None and horas > 0 else None
        gasto_min_usd = custo_usd / minutos if custo_usd is not None and minutos > 0 else None
        gasto_dia_usd = gasto_hora_usd * 24 if gasto_hora_usd is not None else None
        gasto_mes_usd = gasto_hora_usd * 24 * 30 if gasto_hora_usd is not None else None

        def _brl(v):
            return v * taxa if v is not None else None

        ultimos_erros = [
            {"quando": x.criado_em.isoformat() if x.criado_em else None, "origem": x.origem, "erro": x.erro}
            for x in erros[:5]
        ]

        por_conexao.append(
            {
                "connection_id": conn.id,
                "requisicoes": len(logs),
                "erros": len(erros),
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "total_tokens": tt,
                "segundos_uso": round(seg, 1),
                "horas_uso": round(horas, 4),
                "unidades": unidades,
                "tem_preco": p is not None,
                "preco": (
                    {
                        "input": p["input"], "output": p["output"],
                        "por_minuto": p.get("por_minuto"), "moeda": "USD",
                    }
                    if p else None
                ),
                "custo_usd": custo_usd,
                "custo_brl": custo_brl,
                "gasto_min_usd": gasto_min_usd,
                "gasto_min_brl": _brl(gasto_min_usd),
                "gasto_hora_usd": gasto_hora_usd,
                "gasto_hora_brl": _brl(gasto_hora_usd),
                "gasto_dia_usd": gasto_dia_usd,
                "gasto_dia_brl": _brl(gasto_dia_usd),
                "gasto_mes_usd": gasto_mes_usd,
                "gasto_mes_brl": _brl(gasto_mes_usd),
                "ultimos_erros": ultimos_erros,
            }
        )

    return {
        "cotacao_usd_brl": round(taxa, 4),
        "fonte_cotacao": fonte,
        "por_conexao": por_conexao,
    }
