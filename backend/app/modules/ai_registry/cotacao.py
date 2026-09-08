"""Cotação USD→BRL para exibir custo em reais.

O preço dos provedores (Together etc.) é em dólar. Para mostrar em reais, buscamos
a cotação do dia numa fonte grátis (sem chave), com cache em memória de ~1h e uma
cadeia de fontes; se todas falharem, cai num fallback fixo, claramente rotulado.
A cotação é sempre exibida junto do valor, para o número em reais não parecer uma
verdade fixa. Nunca lança — telemetria não pode quebrar por causa do câmbio.
"""

import logging
import time

import httpx

log = logging.getLogger("concursos.ai")

# (nome exibido, url, função que extrai a taxa do JSON)
_FONTES: list[tuple[str, str, object]] = [
    ("open.er-api.com", "https://open.er-api.com/v6/latest/USD", lambda j: float(j["rates"]["BRL"])),
    ("Frankfurter (ECB)", "https://api.frankfurter.dev/v1/latest?base=USD&symbols=BRL",
     lambda j: float(j["rates"]["BRL"])),
]
_FALLBACK = 5.40  # usado só se todas as fontes falharem e não houver cache
_TTL_S = 3600
_cache: dict = {"taxa": None, "ts": 0.0, "fonte": ""}


def usd_brl() -> tuple[float, str]:
    """Devolve (taxa, fonte). Nunca lança."""
    agora = time.time()
    if _cache["taxa"] and agora - _cache["ts"] < _TTL_S:
        return _cache["taxa"], _cache["fonte"]

    for nome, url, pega in _FONTES:
        try:
            r = httpx.get(url, timeout=8, follow_redirects=True)
            r.raise_for_status()
            taxa = pega(r.json())  # type: ignore[operator]
            if taxa <= 0:
                raise ValueError("cotação não positiva")
            _cache.update(taxa=taxa, ts=agora, fonte=nome)
            return taxa, nome
        except Exception as e:  # noqa: BLE001 - tenta a próxima fonte
            log.warning("cotação USD-BRL falhou em %s (%s)", nome, str(e)[:80])

    if _cache["taxa"]:  # última cotação conhecida, mesmo vencida
        return _cache["taxa"], _cache["fonte"] + " (cache)"
    return _FALLBACK, f"fallback fixo (~R$ {_FALLBACK:.2f})"
