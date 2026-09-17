"""Tarefa de fundo: vigia a saúde da ambiente de execucao e, em carga CRÍTICA, avisa o admin por
e-mail e AUTO-BLOQUEIA novos cadastros (para o servidor não quebrar antes de o
usuário decidir migrar). Roda 1x (o serviço tem 1 worker). Nunca derruba o app."""

import asyncio
import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.flags import CADASTROS_BLOQUEADOS, cadastros_bloqueados, set_flag
from app.core.saude import medir
from app.db.models import User
from app.db.session import SessionLocal
from app.integrations.email.enviar import enviar_email

log = logging.getLogger("concursos.monitor")

INTERVALO_S = 180      # checa a cada 3 min
DEBOUNCE_S = 3600      # no máximo 1 alerta por hora
_ultimo_alerta = 0.0


def _registrar_historico_fila(db: Session, m: dict) -> None:
    """[126]: amostra periódica (mesmo ciclo deste monitor) de carga + fila
    de IA — histórico persistido pra o admin decidir quando escalar."""
    from app.db.models import FilaHistorico
    from app.modules.ai_registry.fila import colher_e_zerar, configurado

    amostra = colher_e_zerar()
    cfg = configurado(db)
    db.add(FilaHistorico(
        cpu_pct=round((m["load_por_cpu"] or 0) * 100, 1), memoria_pct=m["memoria_pct"], disco_pct=m["disco_pct"],
        em_voo=amostra["em_voo"], esperando=amostra["esperando"], max_concorrente=cfg["max_concorrente"],
        admitidas=amostra["admitidas"], rejeitadas=amostra["rejeitadas"], espera_media_ms=amostra["espera_media_ms"],
    ))
    db.commit()


def _rodada() -> None:
    global _ultimo_alerta
    db = SessionLocal()
    try:
        m = medir(db)
        _registrar_historico_fila(db, m)
        if m["status"] != "critico" or time.time() - _ultimo_alerta <= DEBOUNCE_S:
            return
        _ultimo_alerta = time.time()
        ja_bloqueado = cadastros_bloqueados(db)
        if not ja_bloqueado:
            set_flag(db, CADASTROS_BLOQUEADOS, "1")
        corpo = (
            "A ambiente de execucao do Simulado Transpetro está em carga CRÍTICA.\n\n"
            f"Motivos: {', '.join(m['motivos']) or '—'}\n"
            f"CPU: {m['load_por_cpu']}/núcleo ({m['cpus']} núcleos) · "
            f"Memória: {m['memoria_pct']}% · Disco: {m['disco_pct']}% · "
            f"Conexões do banco: {m['conexoes_db']}\n\n"
            + ("Novos cadastros foram BLOQUEADOS automaticamente para proteger o servidor.\n"
               if not ja_bloqueado else "Cadastros já estavam bloqueados.\n")
            + "Abra o Perfil → Painel do administrador para acompanhar e reabrir quando resolver."
        )
        admins = db.execute(select(User).where(User.role == "superadmin")).scalars().all()
        for a in admins:
            enviar_email(a.email, "⚠ ambiente de execucao em carga crítica — cadastros bloqueados", corpo)
        log.warning("Saúde CRÍTICA: alerta enviado a %d admin(s); cadastros auto-bloqueados.", len(admins))
    finally:
        db.close()


async def loop_monitor() -> None:
    while True:
        await asyncio.sleep(INTERVALO_S)
        try:
            await asyncio.to_thread(_rodada)  # DB/SMTP síncronos fora do event loop
        except Exception as e:  # noqa: BLE001 - o monitor nunca pode derrubar o app
            log.error("monitor de saúde falhou nesta rodada: %s", e)
