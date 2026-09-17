"""[126]: fila de admissão para chamadas de IA — limita quantas requisições
ficam em voo ao mesmo tempo (semáforo com capacidade editável, padrão 5) e
também segura novas admissões quando CPU/memória/disco da ambiente de execucao estão acima
do limiar configurado ([068] `saude.medir()`). Aplica-se a QUALQUER chamada
de IA que passe por `servico.py` — hoje só as conexões do admin; quando a
API compartilhada da comunidade ([119]) for construída, o mesmo ponto vale
sem precisar mexer aqui de novo, desde que ela continue roteada por
`servico.py`/`resolver.py` (a premissa do próprio desenho do plano).

Não é FIFO estrito: quem espera reavalia periodicamente, sem guardar ordem
de chegada com ticket — decisão de simplicidade. Atende o pedido literal
("sai 1, entra mais 1" = concorrência limitada), não uma fila ordenada.

Funciona corretamente com o único worker uvicorn do serviço ([068], estado
module-level protegido por `threading.Condition`). Se um dia o serviço
passar a rodar com múltiplos workers, isso precisaria virar um mecanismo
entre processos (ex.: Redis) — não construído agora porque não é o cenário
atual.
"""

import threading
import time

from sqlalchemy.orm import Session

from app.core.flags import get_flag, set_flag
from app.core.saude import medir

_PASSO_ESPERA_S = 0.25  # granularidade de reavaliação enquanto uma chamada espera vaga

_cond = threading.Condition()
_em_voo = 0
_esperando = 0

# Contadores acumulados desde a última amostra do histórico — zerados por
# `colher_e_zerar()`, chamada pelo monitor de fundo a cada rodada ([068]).
_admitidas = 0
_rejeitadas = 0
_soma_espera_ms = 0


class FilaEsgotada(Exception):
    """Esperou tempo demais por uma vaga — servidor ocupado, tente de novo.
    Vira 503 via handler global em main.py (não precisa de `except` em cada
    uma das dezenas de rotas que chamam IA)."""


def configurado(db: Session) -> dict:
    return {
        "max_concorrente": int(float(get_flag(db, "fila_max_concorrente", "5") or 5)),
        "cpu_pct_max": float(get_flag(db, "fila_cpu_pct_max", "78") or 78),
        "mem_pct_max": float(get_flag(db, "fila_mem_pct_max", "78") or 78),
        "disco_pct_max": float(get_flag(db, "fila_disco_pct_max", "78") or 78),
        "timeout_espera_s": float(get_flag(db, "fila_timeout_espera_s", "60") or 60),
    }


def salvar_config(
    db: Session, *, max_concorrente: int, cpu_pct_max: float,
    mem_pct_max: float, disco_pct_max: float, timeout_espera_s: float,
) -> dict:
    set_flag(db, "fila_max_concorrente", str(max(1, int(max_concorrente))))
    set_flag(db, "fila_cpu_pct_max", str(max(1.0, cpu_pct_max)))
    set_flag(db, "fila_mem_pct_max", str(max(1.0, mem_pct_max)))
    set_flag(db, "fila_disco_pct_max", str(max(1.0, disco_pct_max)))
    set_flag(db, "fila_timeout_espera_s", str(max(1.0, timeout_espera_s)))
    return configurado(db)


def _recursos(cfg: dict) -> tuple[bool, str | None, dict]:
    """`cpu_pct` é `load_por_cpu × 100` — aproximação (a métrica real do
    monitor de saúde é carga por núcleo, não % literal de ciclo de CPU),
    consistente com o mesmo cálculo já usado em `saude.py`."""
    m = medir()
    cpu_pct = round((m["load_por_cpu"] or 0) * 100, 1)
    memoria_pct = m["memoria_pct"]
    disco_pct = m["disco_pct"]
    valores = {"cpu_pct": cpu_pct, "memoria_pct": memoria_pct, "disco_pct": disco_pct}
    if cpu_pct >= cfg["cpu_pct_max"]:
        return False, f"CPU em {cpu_pct}%", valores
    if memoria_pct is not None and memoria_pct >= cfg["mem_pct_max"]:
        return False, f"memória em {memoria_pct}%", valores
    if disco_pct is not None and disco_pct >= cfg["disco_pct_max"]:
        return False, f"disco em {disco_pct}%", valores
    return True, None, valores


class _Vaga:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.espera_ms = 0

    def __enter__(self) -> "_Vaga":
        global _em_voo, _esperando, _rejeitadas
        inicio = time.monotonic()
        prazo = inicio + self.cfg["timeout_espera_s"]
        with _cond:
            _esperando += 1
            try:
                while True:
                    ok_recurso, motivo_recurso, _ = _recursos(self.cfg)
                    if _em_voo < self.cfg["max_concorrente"] and ok_recurso:
                        _em_voo += 1
                        self.espera_ms = int((time.monotonic() - inicio) * 1000)
                        return self
                    restante = prazo - time.monotonic()
                    if restante <= 0:
                        _rejeitadas += 1
                        motivo = motivo_recurso or f"{self.cfg['max_concorrente']} requisições de IA já em andamento"
                        raise FilaEsgotada(f"Servidor com alta demanda ({motivo}) — tente de novo em instantes.")
                    _cond.wait(timeout=min(_PASSO_ESPERA_S, restante))
            finally:
                _esperando -= 1

    def __exit__(self, exc_type, exc, tb) -> bool:
        global _em_voo, _admitidas, _soma_espera_ms
        with _cond:
            _em_voo -= 1
            _admitidas += 1
            _soma_espera_ms += self.espera_ms
            _cond.notify_all()
        return False


def vaga(db: Session) -> _Vaga:
    return _Vaga(configurado(db))


def estado(db: Session) -> dict:
    """Config + retrato ao vivo, para o painel do admin."""
    cfg = configurado(db)
    _, _, valores = _recursos(cfg)
    with _cond:
        em_voo, esperando = _em_voo, _esperando
    return {**cfg, "em_voo": em_voo, "esperando": esperando, **valores}


def colher_e_zerar() -> dict:
    """Chamada pelo monitor de fundo ([068]) a cada rodada (3 min): devolve
    os contadores acumulados desde a última amostra e zera para a próxima
    janela — é o que alimenta `fila_historico`."""
    global _admitidas, _rejeitadas, _soma_espera_ms
    with _cond:
        admitidas, rejeitadas, soma = _admitidas, _rejeitadas, _soma_espera_ms
        em_voo, esperando = _em_voo, _esperando
        _admitidas = _rejeitadas = _soma_espera_ms = 0
    espera_media_ms = int(soma / admitidas) if admitidas else None
    return {
        "em_voo": em_voo, "esperando": esperando,
        "admitidas": admitidas, "rejeitadas": rejeitadas, "espera_media_ms": espera_media_ms,
    }
