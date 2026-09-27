"""Preço por modelo vindo do PROVEDOR — nunca digitado pelo usuário.

A fonte da verdade é a API. Para provedores OpenAI-compatible (Together), o
`GET {endpoint}/models` traz `pricing` por modelo, em USD:
  - `input`  — por 1M (tokens em chat/embeddings; caracteres em TTS)
  - `output` — por 1M tokens
  - `transcribe.price_per_minute` — por minuto (STT)

Cache por plataforma (~1h). Nunca lança: sem rede/sem chave/local → {} e o custo
fica indisponível (nunca vira campo para preencher).
"""

import logging
import time

import httpx

from app.core.crypto import decifrar_ia

log = logging.getLogger("concursos.ai")

_TTL_S = 3600
# [170] Falha de preço também é lembrada, por pouco tempo. Antes cada tentativa
# falha esperava até 20 s e se repetia a CADA chamada de IA (o teto de orçamento
# consulta os preços em toda requisição) — se o `/models` do provedor ficasse
# lento, o app inteiro ficava lento junto.
_RETRY_APOS_FALHA_S = 60
_cache: dict[int, dict] = {}  # platform_id -> {"ts": float, "precos": {model_lower: {...}}}


def _buscar(plat) -> dict:
    base = (plat.endpoint or "").rstrip("/")
    if not base or base.startswith("local://"):
        return {}
    chave = decifrar_ia(plat.api_key_cifrada) if plat.api_key_cifrada else ""
    headers = {"Authorization": f"Bearer {chave}"} if chave else {}
    r = httpx.get(base + "/models", headers=headers, timeout=20, follow_redirects=True)
    r.raise_for_status()
    data = r.json()
    itens = data if isinstance(data, list) else data.get("data", [])
    out: dict[str, dict] = {}
    for m in itens:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "")
        if not mid:
            continue
        pr = m.get("pricing") or {}
        transc = pr.get("transcribe")
        por_min = transc.get("price_per_minute") if isinstance(transc, dict) else None
        out[mid.lower()] = {
            "input": float(pr.get("input") or 0),
            "output": float(pr.get("output") or 0),
            "por_minuto": float(por_min) if por_min else None,
            "type": m.get("type"),
        }
    return out


def precos_da_plataforma(plat) -> dict:
    """{model_id_lower: {input, output, por_minuto, type}} em USD, ou {} se indisponível."""
    agora = time.time()
    c = _cache.get(plat.id)
    if c and agora - c["ts"] < _TTL_S:
        return c["precos"]
    try:
        precos = _buscar(plat)
        _cache[plat.id] = {"ts": agora, "precos": precos}
        return precos
    except Exception as e:  # noqa: BLE001 - preço é best-effort; sem ele o custo fica "—"
        log.warning("preços do provedor indisponíveis (plataforma %s): %s", plat.id, str(e)[:120])
        anteriores = c["precos"] if c else {}
        _cache[plat.id] = {"ts": agora - _TTL_S + _RETRY_APOS_FALHA_S, "precos": anteriores}
        return anteriores
