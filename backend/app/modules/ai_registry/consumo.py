"""[170] Consumo de IA por usuário e por ferramenta, na unidade que a API cobra.

Serve para DEFINIR limites com dado real, não para aplicá-los. Tudo é derivado do
`ai_call_log` × preço da API na hora da leitura (custo nunca é gravado).

Regras de justiça, que estão aqui e não na tela:

- A unidade de análise é a AÇÃO do usuário (`acao_id`): uma mensagem de voz é uma
  ação, mesmo gerando transcrição + busca + LLM + voz. Contar chamadas brutas
  puniria a pessoa por como o sistema é montado.
- Ação que não entregou resposta NÃO conta como ação (o custo dela continua
  aparecendo — foi gasto de verdade). Vale a ação que teve ao menos uma resposta
  de texto/visão bem-sucedida; sem chamada de texto (ex.: só transcrever), vale se
  qualquer chamada deu certo.
- As distribuições que orientam o limite (mediana, p90) são calculadas SÓ sobre
  clientes. Dono e vitalício aparecem no painel, marcados, mas ficam fora delas —
  senão o teste de um QA entortaria o número que vai valer para quem paga.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AiCallLog, AiConnection, User
from app.modules.ai_registry.cotacao import usd_brl
from app.modules.ai_registry.precos import precos_da_plataforma
from app.modules.ai_registry.telemetria import _custo_usd

MAX_DIAS = 90


def _pct(valores: list[float], q: float) -> float | None:
    """Percentil por interpolação linear. None se não há dado."""
    if not valores:
        return None
    v = sorted(valores)
    if len(v) == 1:
        return v[0]
    pos = (len(v) - 1) * q
    i = int(pos)
    frac = pos - i
    return v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * frac


def _dist(valores: list[float]) -> dict:
    return {
        "n": len(valores),
        "p50": _pct(valores, 0.5), "p90": _pct(valores, 0.9),
        "max": max(valores) if valores else None,
    }


def _zero() -> dict:
    return {"chamadas": 0, "falhas": 0, "tokens_in": 0, "tokens_out": 0, "stt_seg": 0,
            "tts_chars": 0, "custo_usd": 0.0}


def _somar(dest: dict, chamadas: int, sucessos: int, pt: int, ct: int, tipo: str | None, un: int,
           custo: float) -> None:
    dest["chamadas"] += chamadas
    dest["falhas"] += chamadas - sucessos
    dest["tokens_in"] += pt
    dest["tokens_out"] += ct
    if tipo == "segundos":
        dest["stt_seg"] += un
    elif tipo == "caracteres":
        dest["tts_chars"] += un
    dest["custo_usd"] += custo


def resumo(db: Session, dias: int = 7) -> dict:
    dias = max(1, min(int(dias), MAX_DIAS))
    agora = datetime.now(UTC)
    desde = agora - timedelta(days=dias)
    taxa, fonte = usd_brl()

    dia = func.date(func.timezone("UTC", AiCallLog.criado_em))
    linhas = db.execute(
        select(
            AiCallLog.user_id, AiCallLog.ferramenta, dia, AiCallLog.acao_id,
            AiCallLog.connection_id, AiCallLog.tipo_unidade,
            func.count(),
            func.count().filter(AiCallLog.sucesso.is_(True)),
            func.coalesce(func.sum(AiCallLog.prompt_tokens), 0),
            func.coalesce(func.sum(AiCallLog.completion_tokens), 0),
            func.coalesce(func.sum(AiCallLog.unidades), 0),
        )
        .where(AiCallLog.criado_em >= desde)
        .group_by(AiCallLog.user_id, AiCallLog.ferramenta, dia, AiCallLog.acao_id,
                  AiCallLog.connection_id, AiCallLog.tipo_unidade)
    ).all()

    conns = {c.id: c for c in db.execute(select(AiConnection)).scalars()}
    precos: dict[int, dict] = {}

    def custo_da_linha(cid, pt, ct, tipo, un) -> float:
        conn = conns.get(cid)
        if not conn:
            return 0.0
        if conn.platform_id not in precos:
            precos[conn.platform_id] = precos_da_plataforma(conn.plataforma)
        c, _ = _custo_usd(conn, precos[conn.platform_id], pt, ct, {tipo: un} if tipo and un else {})
        return c or 0.0

    acoes: dict[tuple, dict] = {}
    por_ferr: dict[str, dict] = defaultdict(_zero)
    por_user: dict[int | None, dict] = defaultdict(lambda: {"total": _zero(), "ferr": defaultdict(_zero)})
    for uid, ferr, d, acao, cid, tipo, n, ok, pt, ct, un in linhas:
        ferr = ferr or "sem_ferramenta"
        custo = custo_da_linha(cid, pt, ct, tipo, un)
        _somar(por_ferr[ferr], n, ok, pt, ct, tipo, un, custo)
        _somar(por_user[uid]["total"], n, ok, pt, ct, tipo, un, custo)
        _somar(por_user[uid]["ferr"][ferr], n, ok, pt, ct, tipo, un, custo)

        # ação: sem `acao_id` (histórico) cada (usuário, ferramenta, dia) vira uma
        # ação-agregado — melhor que inventar; o painel avisa que é histórico.
        chave = (uid, ferr, acao) if acao else (uid, ferr, f"hist-{d}")
        a = acoes.setdefault(chave, {"uid": uid, "ferr": ferr, "dia": d, "custo": 0.0,
                                     "ok_texto": False, "ok_qualquer": False, "tem_texto": False,
                                     "historico": acao is None})
        a["custo"] += custo
        cat = conns[cid].categoria if cid in conns else None
        if cat in ("texto", "visao"):
            a["tem_texto"] = True
            a["ok_texto"] = a["ok_texto"] or ok > 0
        a["ok_qualquer"] = a["ok_qualquer"] or ok > 0

    def valida(a: dict) -> bool:
        return a["ok_texto"] if a["tem_texto"] else a["ok_qualquer"]

    users = {u.id: u for u in db.execute(
        select(User).where(User.id.in_([u for u in por_user if u is not None]))
    ).scalars()} if any(u is not None for u in por_user) else {}

    def cliente(uid) -> bool:
        u = users.get(uid)
        return u is not None and not u.sem_limites

    # ações por ferramenta (todas as pessoas) e distribuições só de clientes
    acoes_ferr: dict[str, dict] = defaultdict(lambda: {"validas": 0, "falhas": 0, "custos_clientes": []})
    dia_user: dict[tuple, dict] = defaultdict(lambda: {"custo": 0.0, "acoes": 0})
    acoes_user_ferr: dict[tuple, int] = defaultdict(int)
    for a in acoes.values():
        if a["historico"]:
            # Sem `acao_id` não dá para saber quantas ações foram: NÃO conto ação
            # (colapsar 60 chamadas em "1 ação" enganaria). O custo, que é real,
            # continua nos totais e no custo por usuário-dia.
            if cliente(a["uid"]):
                dia_user[(a["uid"], a["dia"])]["custo"] += a["custo"]
            continue
        af = acoes_ferr[a["ferr"]]
        if valida(a):
            af["validas"] += 1
            acoes_user_ferr[(a["uid"], a["ferr"])] += 1
            if cliente(a["uid"]):
                af["custos_clientes"].append(a["custo"])
        else:
            af["falhas"] += 1
        if cliente(a["uid"]):
            dia_user[(a["uid"], a["dia"])]["custo"] += a["custo"]
            dia_user[(a["uid"], a["dia"])]["acoes"] += 1 if valida(a) else 0

    def money(usd: float) -> dict:
        return {"usd": round(usd, 6), "brl": round(usd * taxa, 6)}

    def fmt(t: dict) -> dict:
        return {**{k: t[k] for k in ("chamadas", "falhas", "tokens_in", "tokens_out", "stt_seg", "tts_chars")},
                "custo": money(t["custo_usd"])}

    ferramentas = []
    for ferr, t in sorted(por_ferr.items(), key=lambda kv: -kv[1]["custo_usd"]):
        af = acoes_ferr[ferr]
        custos = af["custos_clientes"]
        ferramentas.append({
            "ferramenta": ferr, **fmt(t),
            "acoes": af["validas"], "acoes_falhas": af["falhas"],
            "custo_por_acao_clientes": {
                **{k: (money(v) if isinstance(v, float) else v) for k, v in _dist(custos).items()},
            },
        })

    usuarios = []
    for uid, blocos in sorted(por_user.items(), key=lambda kv: -kv[1]["total"]["custo_usd"]):
        u = users.get(uid)
        dias_do_user = sorted(d for (x, d) in dia_user if x == uid) if cliente(uid) else []
        usuarios.append({
            "user_id": uid,
            "nome": u.nome if u else ("(sem usuário — histórico/sistema)" if uid is None else f"#{uid}"),
            "email": u.email if u else None,
            "sem_limites": bool(u and u.sem_limites),
            "total": fmt(blocos["total"]),
            "por_ferramenta": [
                {"ferramenta": f, **fmt(t), "acoes": acoes_user_ferr.get((uid, f), 0)}
                for f, t in sorted(blocos["ferr"].items(), key=lambda kv: -kv[1]["custo_usd"])
            ],
            "dias_ativos": len(dias_do_user),
        })

    custos_dia = [v["custo"] for v in dia_user.values()]
    acoes_dia = [float(v["acoes"]) for v in dia_user.values()]
    dist_dia = {k: (money(v) if isinstance(v, float) else v) for k, v in _dist(custos_dia).items()}
    dist_acoes = _dist(acoes_dia)

    return {
        "dias": dias, "desde": desde.isoformat(),
        "cotacao": {"usd_brl": taxa, "fonte": fonte},
        "total": money(sum(t["custo_usd"] for t in por_ferr.values())),
        "ferramentas": ferramentas,
        "usuarios": usuarios,
        "distribuicao_clientes": {
            "usuarios_com_uso": len({u for (u, _) in dia_user}),
            "custo_por_usuario_dia": dist_dia,
            "acoes_por_usuario_dia": dist_acoes,
        },
        "notas": [
            "Custo derivado na leitura: uso × preço atual da API.",
            "Ação = uma interação do usuário (uma mensagem de voz é uma ação, mesmo com 3-4 chamadas por trás).",
            "Ação sem resposta entregue não conta como ação; o custo dela continua somado.",
            "Distribuições consideram só clientes (dono e vitalício ficam de fora).",
            "Linhas anteriores ao registro (sem ferramenta e sem acao_id) entram nos totais e no custo,"
            " mas NÃO são contadas como ações.",
        ],
    }
