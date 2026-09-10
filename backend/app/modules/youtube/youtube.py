"""Busca REAL de vídeos no YouTube (YouTube Data API v3) — não um link cego.

A chave é global, cifrada no banco (mesma cripto das conexões de IA e das
plataformas de pagamento). Nunca aparece em log nem em mensagem de erro. Sem
chave configurada, o chamador deve cair no link de busca simples (fallback que
não depende disto)."""

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import cifrar_ia, decifrar_ia, mascarar_chave
from app.db.models import YoutubeConfig

BUSCA_URL = "https://www.googleapis.com/youtube/v3/search"


class YoutubeError(Exception):
    pass


def _config(db: Session) -> YoutubeConfig | None:
    return db.execute(select(YoutubeConfig)).scalars().first()


def configurada(db: Session) -> bool:
    return _config(db) is not None


def chave_mascarada(db: Session) -> str | None:
    c = _config(db)
    if not c:
        return None
    try:
        return mascarar_chave(decifrar_ia(c.chave_cifrada))
    except Exception:  # noqa: BLE001
        return "****"


def salvar_chave(db: Session, chave_texto: str) -> None:
    c = _config(db)
    cifrada = cifrar_ia(chave_texto.strip())
    if c:
        c.chave_cifrada = cifrada
    else:
        db.add(YoutubeConfig(chave_cifrada=cifrada))
    db.commit()


def apagar_chave(db: Session) -> None:
    c = _config(db)
    if c:
        db.delete(c)
        db.commit()


def _buscar_com_chave(chave: str, query: str, max_resultados: int) -> list[dict]:
    try:
        r = httpx.get(
            BUSCA_URL,
            params={
                "part": "snippet", "type": "video", "q": query,
                "maxResults": max(1, min(max_resultados, 8)),
                "relevanceLanguage": "pt", "safeSearch": "moderate", "key": chave,
            },
            timeout=15,
        )
    except httpx.HTTPError as e:
        raise YoutubeError(f"Falha ao contatar o YouTube: {e}") from e

    if r.status_code == 403:
        raise YoutubeError("A chave foi recusada ou a cota diária da API esgotou.")
    if r.status_code != 200:
        raise YoutubeError(f"O YouTube devolveu erro {r.status_code}.")

    itens = r.json().get("items", [])
    resultados = []
    for it in itens:
        vid = it.get("id", {}).get("videoId")
        sn = it.get("snippet", {})
        if not vid:
            continue
        miniaturas = sn.get("thumbnails", {})
        miniatura = (miniaturas.get("medium") or miniaturas.get("default") or {}).get("url", "")
        resultados.append({
            "video_id": vid,
            "titulo": sn.get("title", ""),
            "canal": sn.get("channelTitle", ""),
            "miniatura": miniatura,
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return resultados


def buscar(db: Session, query: str, max_resultados: int = 4) -> list[dict]:
    c = _config(db)
    if not c:
        raise YoutubeError("YouTube ainda não foi configurado.")
    chave = decifrar_ia(c.chave_cifrada)
    return _buscar_com_chave(chave, query, max_resultados)


def testar(db: Session) -> dict:
    """Prova que a chave salva funciona: busca de verdade, não só formato."""
    c = _config(db)
    if not c:
        return {"ok": False, "mensagem": "Nenhuma chave salva ainda."}
    chave = decifrar_ia(c.chave_cifrada)
    try:
        resultados = _buscar_com_chave(chave, "aula de matemática", 1)
    except YoutubeError as e:
        return {"ok": False, "mensagem": str(e)}
    return {"ok": True, "mensagem": f"Conectado — {len(resultados)} resultado(s) na busca de teste."}
