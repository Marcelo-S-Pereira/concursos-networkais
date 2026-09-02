"""Resolve QUAL conexão usar para uma categoria.

Regra (skill_conexao_padrao_LLM.md): a "ativa" é a posição 1. As demais só
entram no fallback automático se tiverem `ordem_fallback` preenchida (2, 3...).
Sem nenhuma numerada, não há fallback — falhou, o ciclo falha. A cadeia é
resolvida UMA vez por chamada (não a cada retentativa).
"""

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AiConnection

CATEGORIAS = ("texto", "visao", "embeddings", "transcricao")

_cache: dict[str, tuple[float, list[AiConnection]]] = {}
_TTL = 60.0  # segundos


def invalidar_cache() -> None:
    _cache.clear()


def cadeia_para_categoria(db: Session, categoria: str) -> list[AiConnection]:
    agora = time.monotonic()
    em_cache = _cache.get(categoria)
    if em_cache and em_cache[0] > agora:
        return em_cache[1]

    todas = list(db.execute(select(AiConnection).where(AiConnection.categoria == categoria)).scalars())
    ativa = next((c for c in todas if c.ativa), None)
    if not ativa:
        cadeia: list[AiConnection] = []
    else:
        resto = sorted(
            (c for c in todas if not c.ativa and c.ordem_fallback is not None),
            key=lambda c: c.ordem_fallback or 0,
        )
        cadeia = [ativa, *resto]

    _cache[categoria] = (agora + _TTL, cadeia)
    return cadeia
