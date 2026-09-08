"""Saúde da ambiente de execucao: carga de CPU, memória, disco e conexões do Postgres.

Sem dependência externa (nada de psutil): usa os.getloadavg, /proc/meminfo e
shutil.disk_usage. Classifica em ok / atencao / critico por limiares, para avisar
o admin antes de o servidor quebrar."""

import os
import shutil

from sqlalchemy import text
from sqlalchemy.orm import Session

_ORDEM = {"ok": 0, "atencao": 1, "critico": 2}


def _memoria_pct() -> float | None:
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for linha in f:
                chave, resto = linha.split(":", 1)
                info[chave.strip()] = int(resto.strip().split()[0])  # kB
        total = info.get("MemTotal", 0)
        disponivel = info.get("MemAvailable", info.get("MemFree", 0))
        return round((total - disponivel) / total * 100, 1) if total else None
    except Exception:  # noqa: BLE001
        return None


def _nivel(valor: float | None, atencao: float, critico: float) -> str:
    if valor is None:
        return "ok"
    if valor >= critico:
        return "critico"
    if valor >= atencao:
        return "atencao"
    return "ok"


def medir(db: Session | None = None) -> dict:
    cpus = os.cpu_count() or 1
    load1 = os.getloadavg()[0]
    load_por_cpu = round(load1 / cpus, 2)
    memoria = _memoria_pct()
    try:
        uso = shutil.disk_usage("/")
        disco = round(uso.used / uso.total * 100, 1)
    except Exception:  # noqa: BLE001
        disco = None
    conexoes = None
    if db is not None:
        try:
            conexoes = db.execute(text("SELECT count(*) FROM pg_stat_activity")).scalar()
        except Exception:  # noqa: BLE001
            conexoes = None

    st_load = _nivel(load_por_cpu, 0.85, 1.3)
    st_mem = _nivel(memoria, 85, 95)
    st_disco = _nivel(disco, 85, 95)
    status = max([st_load, st_mem, st_disco], key=lambda s: _ORDEM[s])

    motivos = []
    if st_load != "ok":
        motivos.append(f"carga de CPU {load_por_cpu}/núcleo")
    if st_mem != "ok" and memoria is not None:
        motivos.append(f"memória {memoria}%")
    if st_disco != "ok" and disco is not None:
        motivos.append(f"disco {disco}%")

    return {
        "cpus": cpus,
        "load_1min": round(load1, 2),
        "load_por_cpu": load_por_cpu,
        "memoria_pct": memoria,
        "disco_pct": disco,
        "conexoes_db": conexoes,
        "status": status,
        "motivos": motivos,
    }
