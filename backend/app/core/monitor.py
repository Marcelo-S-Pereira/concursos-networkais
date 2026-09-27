"""Tarefa de fundo: vigia a saúde da ambiente de execucao e, em carga CRÍTICA, avisa o admin por
e-mail e AUTO-BLOQUEIA novos cadastros (para o servidor não quebrar antes de o
usuário decidir migrar). Roda 1x (o serviço tem 1 worker). Nunca derruba o app."""

import asyncio
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path

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

# [176] O script scripts/backup_concursos.sh grava aqui "OK <data> dump=<bytes>" ou "FALHA <data> <motivo>".
STATUS_BACKUP = Path(os.environ.get("BACKUP_STATUS_ARQUIVO", "/opt/app/.backup_concursos/status"))
BACKUP_MAX_IDADE_H = 26   # o backup roda a cada 24 h; 2 h de folga
DEBOUNCE_BACKUP_S = 6 * 3600
_ultimo_alerta_backup = 0.0


def problema_de_backup(caminho: Path = STATUS_BACKUP, agora: datetime | None = None) -> str | None:
    """None = backup em dia. Backup que falha calado é a falha clássica — por isso o
    monitor confere o status a cada rodada em vez de confiar no cron."""
    try:
        linha = caminho.read_text().strip().splitlines()[0]
    except (OSError, IndexError):
        return "não há registro de nenhum backup (arquivo de status ausente ou vazio)"
    situacao, _, resto = linha.partition(" ")
    quando, _, detalhe = resto.partition(" ")
    if situacao == "FALHA":
        return f"o último backup FALHOU ({quando}): {detalhe}"
    try:
        momento = datetime.fromisoformat(quando.replace("Z", "+00:00"))
    except ValueError:
        return "o arquivo de status do backup está ilegível"
    idade_h = ((agora or datetime.now(UTC)) - momento).total_seconds() / 3600
    if idade_h > BACKUP_MAX_IDADE_H:
        return f"o último backup bom tem {idade_h:.0f} h (o limite é {BACKUP_MAX_IDADE_H} h)"
    return None


def _verificar_backup(db: Session) -> None:
    global _ultimo_alerta_backup
    problema = problema_de_backup()
    if not problema or time.time() - _ultimo_alerta_backup <= DEBOUNCE_BACKUP_S:
        return
    _ultimo_alerta_backup = time.time()
    corpo = (
        "O backup do ConcurseiroIA precisa de atenção:\n\n"
        f"{problema}\n\n"
        "Veja /opt/app/backup_concursos.log na ambiente de execucao e rode scripts/backup_concursos.sh à mão. "
        "Enquanto isso, os dados de usuários, créditos e conversas estão sem cópia recente."
    )
    admins = db.execute(select(User).where(User.role == "superadmin")).scalars().all()
    for a in admins:
        enviar_email(a.email, "⚠ Backup do ConcurseiroIA com problema", corpo)
    log.warning("Backup com problema (%s): alerta enviado a %d admin(s).", problema, len(admins))


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
        _verificar_backup(db)  # antes do retorno antecipado abaixo: vale mesmo com a ambiente de execucao saudável
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
