"""Log de uso de IA. NUNCA lança — telemetria não pode derrubar a resposta."""

import logging

from sqlalchemy.orm import Session

from app.db.models import AiCallLog

log = logging.getLogger("concursos.ai")


def registrar(
    db: Session,
    *,
    connection_id: int | None,
    categoria: str,
    origem: str,
    modelo: str,
    sucesso: bool,
    latencia_ms: int,
    usage: dict | None = None,
    unidades: int | None = None,
    tipo_unidade: str | None = None,
    erro: str | None = None,
) -> None:
    try:
        usage = usage or {}
        db.add(
            AiCallLog(
                connection_id=connection_id,
                categoria=categoria,
                origem=origem,
                modelo=modelo,
                sucesso=sucesso,
                latencia_ms=latencia_ms,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                unidades=unidades,
                tipo_unidade=tipo_unidade,
                erro=(erro or "")[:500] or None,
            )
        )
        db.commit()
    except Exception as e:  # noqa: BLE001 - telemetria é best-effort
        db.rollback()
        log.error("falha ao gravar ai_call_log (resposta ao usuário não afetada): %s", e)
