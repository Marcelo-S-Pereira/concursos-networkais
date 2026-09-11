"""Chamada a provedor OpenAI-compatible, com a robustez concentrada num ponto.

Reimplementa em Python (httpx) o que o network-ais faz em TS:
- timeout finito;
- 1 retry em 429 respeitando Retry-After (inclusive embutido no texto);
- retry sem `reasoning_effort` quando o provedor rejeita o campo com 400;
- erro explícito em resposta sem conteúdo, carregando o usage;
- captura o usage reportado pela API.
"""

import re
import time

import httpx

from app.core.crypto import decifrar_ia
from app.db.models import AiConnection

TIMEOUT_S = 180.0
RATE_LIMIT_MAX_WAIT_S = 30.0


class AiCallError(Exception):
    def __init__(self, mensagem: str, usage: dict | None = None):
        super().__init__(mensagem)
        self.usage = usage or {}


def _headers(chave: str) -> dict:
    h = {"Content-Type": "application/json"}
    if chave:
        h["Authorization"] = f"Bearer {chave}"
    return h


def _espera_retry(resp: httpx.Response, corpo: str) -> float:
    ra = resp.headers.get("retry-after")
    if ra:
        try:
            return min(float(ra), RATE_LIMIT_MAX_WAIT_S)
        except ValueError:
            pass
    m = re.search(r"try again in ([\d.]+)\s*s", corpo, re.I)
    if m:
        return min(float(m.group(1)), RATE_LIMIT_MAX_WAIT_S)
    return RATE_LIMIT_MAX_WAIT_S / 2


def _parse_usage(data: dict) -> dict:
    u = data.get("usage") or {}
    pt = u.get("prompt_tokens") or 0
    ct = u.get("completion_tokens") or 0
    return {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": u.get("total_tokens") or (pt + ct)}


def chamar_chat(
    conn: AiConnection,
    mensagens: list[dict],
    *,
    max_tokens: int | None = None,
    enviar_reasoning: bool = True,
    _retries: int = 1,
) -> tuple[str, dict]:
    """Retorna (conteúdo, usage). `mensagens` no formato OpenAI. Serve texto e
    visão — visão é a mesma rota, com parte `image_url` dentro do content."""
    if conn.endpoint.startswith("local://"):
        raise AiCallError(
            f'"{conn.nome}" é um modelo LOCAL (roda na ambiente de execucao) — a execução do motor local '
            "ainda não está ligada (vem com o tutor por voz). O cadastro já está salvo."
        )
    chave = decifrar_ia(conn.api_key_cifrada)
    corpo_req: dict = {
        "model": conn.modelo,
        "messages": mensagens,
        "max_tokens": max_tokens or conn.max_tokens,
        "temperature": conn.temperatura,
    }
    if enviar_reasoning:
        corpo_req["reasoning_effort"] = "low"

    url = conn.endpoint.rstrip("/") + "/chat/completions"
    try:
        resp = httpx.post(url, headers=_headers(chave), json=corpo_req, timeout=TIMEOUT_S)
    except httpx.TimeoutException as e:
        raise AiCallError(f'"{conn.nome}" não respondeu em {int(TIMEOUT_S)}s.') from e
    except httpx.HTTPError as e:
        raise AiCallError(f'Falha ao conectar a "{conn.nome}": {e}') from e

    if resp.status_code != 200:
        texto = resp.text[:400]
        if resp.status_code == 429 and _retries > 0:
            time.sleep(_espera_retry(resp, texto))
            return chamar_chat(conn, mensagens, max_tokens=max_tokens,
                               enviar_reasoning=enviar_reasoning, _retries=_retries - 1)
        if enviar_reasoning and resp.status_code == 400 and re.search(r"reasoning|thinking", texto, re.I):
            return chamar_chat(conn, mensagens, max_tokens=max_tokens, enviar_reasoning=False, _retries=_retries)
        raise AiCallError(f'"{conn.nome}" respondeu {resp.status_code}: {texto}')

    data = resp.json()
    usage = _parse_usage(data)
    conteudo = (data.get("choices") or [{}])[0].get("message", {}).get("content")
    if not conteudo:
        # Modelo raciocinador pode gastar o max_tokens inteiro "pensando" e não
        # escrever content. O erro carrega o usage para a falha ser contável.
        raise AiCallError(f'"{conn.nome}" respondeu sem conteúdo (max_tokens curto para modelo que raciocina?).', usage)
    return conteudo, usage


def transcrever(conn: AiConnection, audio_bytes: bytes, nome_arquivo: str, *, idioma: str = "pt") -> dict:
    """STT. Retorna {"texto": str, "duracao_s": float}. `response_format=verbose_json`
    para vir a duração real (usada no custo em crédito, cobrado por tempo)."""
    if conn.endpoint.startswith("local://"):
        raise AiCallError(f'"{conn.nome}" é um modelo LOCAL — execução do motor local ainda não ligada.')
    chave = decifrar_ia(conn.api_key_cifrada)
    url = conn.endpoint.rstrip("/") + "/audio/transcriptions"
    headers = {"Authorization": f"Bearer {chave}"} if chave else {}
    try:
        resp = httpx.post(
            url, headers=headers, files={"file": (nome_arquivo, audio_bytes)},
            data={"model": conn.modelo, "language": idioma, "response_format": "verbose_json"},
            timeout=TIMEOUT_S,
        )
    except httpx.TimeoutException as e:
        raise AiCallError(f'"{conn.nome}" não respondeu em {int(TIMEOUT_S)}s.') from e
    except httpx.HTTPError as e:
        raise AiCallError(f'Falha ao conectar a "{conn.nome}": {e}') from e
    if resp.status_code != 200:
        raise AiCallError(f'"{conn.nome}" respondeu {resp.status_code}: {resp.text[:400]}')
    data = resp.json()
    texto = (data.get("text") or "").strip()
    if not texto:
        raise AiCallError(f'"{conn.nome}" não transcreveu nada (áudio vazio ou silencioso?).')
    return {"texto": texto, "duracao_s": float(data.get("duration") or 0)}


def falar(conn: AiConnection, texto: str, voz: str, *, formato: str = "mp3") -> bytes:
    """TTS. Retorna os BYTES do áudio (a API devolve binário direto, não JSON)."""
    if conn.endpoint.startswith("local://"):
        raise AiCallError(f'"{conn.nome}" é um modelo LOCAL — execução do motor local ainda não ligada.')
    chave = decifrar_ia(conn.api_key_cifrada)
    url = conn.endpoint.rstrip("/") + "/audio/speech"
    corpo = {"model": conn.modelo, "input": texto, "voice": voz, "response_format": formato, "stream": False}
    try:
        resp = httpx.post(url, headers=_headers(chave), json=corpo, timeout=TIMEOUT_S)
    except httpx.TimeoutException as e:
        raise AiCallError(f'"{conn.nome}" não respondeu em {int(TIMEOUT_S)}s.') from e
    except httpx.HTTPError as e:
        raise AiCallError(f'Falha ao conectar a "{conn.nome}": {e}') from e
    if resp.status_code != 200:
        raise AiCallError(f'"{conn.nome}" respondeu {resp.status_code}: {resp.text[:400]}')
    if not resp.content:
        raise AiCallError(f'"{conn.nome}" devolveu áudio vazio.')
    return resp.content


def chamar_embeddings(conn: AiConnection, textos: list[str]) -> tuple[list[list[float]], dict]:
    if conn.endpoint.startswith("local://"):
        raise AiCallError(f'"{conn.nome}" é um modelo LOCAL — execução do motor local ainda não ligada.')
    chave = decifrar_ia(conn.api_key_cifrada)
    url = conn.endpoint.rstrip("/") + "/embeddings"
    try:
        resp = httpx.post(url, headers=_headers(chave), json={"model": conn.modelo, "input": textos}, timeout=TIMEOUT_S)
    except httpx.HTTPError as e:
        raise AiCallError(f'Falha em embeddings de "{conn.nome}": {e}') from e
    if resp.status_code != 200:
        raise AiCallError(f'"{conn.nome}" (embeddings) respondeu {resp.status_code}: {resp.text[:300]}')
    data = resp.json()
    vetores = [d.get("embedding") for d in (data.get("data") or [])]
    if len(vetores) != len(textos) or any(v is None for v in vetores):
        raise AiCallError(f'"{conn.nome}" devolveu embeddings em formato inesperado.')
    return vetores, _parse_usage(data)
