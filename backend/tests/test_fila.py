"""[126]: fila de admissão para chamadas de IA — teto de concorrência
editável + gate por CPU/memória/disco, com timeout de espera. Testado com
threads reais (não só mock de contagem), porque é exatamente a concorrência
que está em jogo aqui."""

import threading
import time
import unittest.mock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import apenas_superadmin
from app.db.models import User
from app.main import app
from app.modules.ai_registry import fila

_RECURSOS_OK = {"load_por_cpu": 0.1, "memoria_pct": 10.0, "disco_pct": 10.0}


def _admin_falso() -> User:
    return User(id=1, nome="Admin Teste", email="admin@fila_test.local", role="superadmin")


def test_max_concorrente_e_respeitado_com_threads_reais():
    cfg = {"max_concorrente": 2, "cpu_pct_max": 100, "mem_pct_max": 100, "disco_pct_max": 100, "timeout_espera_s": 5}
    pico = {"valor": 0}
    contagem_lock = threading.Lock()

    with unittest.mock.patch.object(fila, "configurado", return_value=cfg), \
         unittest.mock.patch.object(fila, "medir", return_value=_RECURSOS_OK):

        def trabalho():
            with fila.vaga(db=None):
                with contagem_lock:
                    pico["valor"] = max(pico["valor"], fila._em_voo)
                time.sleep(0.2)

        threads = [threading.Thread(target=trabalho) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert pico["valor"] == 2  # 5 threads, teto 2 — nunca deveria passar disso
    assert fila._em_voo == 0  # todas as vagas liberadas ao final


def test_sai_um_entra_mais_um():
    """Teto 1: a 2ª requisição só é admitida depois que a 1ª libera."""
    cfg = {"max_concorrente": 1, "cpu_pct_max": 100, "mem_pct_max": 100, "disco_pct_max": 100, "timeout_espera_s": 5}
    eventos: list[tuple[str, float]] = []
    inicio = time.monotonic()

    with unittest.mock.patch.object(fila, "configurado", return_value=cfg), \
         unittest.mock.patch.object(fila, "medir", return_value=_RECURSOS_OK):

        def primeira():
            with fila.vaga(db=None):
                eventos.append(("A entrou", time.monotonic() - inicio))
                time.sleep(0.4)
            eventos.append(("A saiu", time.monotonic() - inicio))

        def segunda():
            time.sleep(0.1)  # garante que A já entrou primeiro
            with fila.vaga(db=None):
                eventos.append(("B entrou", time.monotonic() - inicio))

        ta, tb = threading.Thread(target=primeira), threading.Thread(target=segunda)
        ta.start()
        tb.start()
        ta.join()
        tb.join()

    ordem = [nome for nome, _ in eventos]
    assert ordem == ["A entrou", "A saiu", "B entrou"], ordem
    tempo_b = next(t for nome, t in eventos if nome == "B entrou")
    assert tempo_b >= 0.35  # B só entrou depois que A liberou (~0.4s), não nos 0.1s iniciais


def test_timeout_gera_filaesgotada_por_concorrencia():
    cfg = {"max_concorrente": 1, "cpu_pct_max": 100, "mem_pct_max": 100, "disco_pct_max": 100, "timeout_espera_s": 0.3}
    # fila.vaga do meio ocupa a única vaga e segura; a última estoura o timeout
    with unittest.mock.patch.object(fila, "configurado", return_value=cfg), \
         unittest.mock.patch.object(fila, "medir", return_value=_RECURSOS_OK), \
         fila.vaga(db=None), pytest.raises(fila.FilaEsgotada) as ei, fila.vaga(db=None):
        pass
    assert "em andamento" in str(ei.value)


def test_recurso_acima_do_limiar_bloqueia_admissao():
    cfg = {"max_concorrente": 5, "cpu_pct_max": 78, "mem_pct_max": 78, "disco_pct_max": 78, "timeout_espera_s": 0.3}
    recursos_ruins = {"load_por_cpu": 0.1, "memoria_pct": 95.0, "disco_pct": 10.0}
    with unittest.mock.patch.object(fila, "configurado", return_value=cfg), \
         unittest.mock.patch.object(fila, "medir", return_value=recursos_ruins), \
         pytest.raises(fila.FilaEsgotada) as ei, fila.vaga(db=None):
        pass
    assert "memória" in str(ei.value)


def test_colher_e_zerar_conta_admitidas_e_rejeitadas():
    cfg = {"max_concorrente": 1, "cpu_pct_max": 100, "mem_pct_max": 100, "disco_pct_max": 100, "timeout_espera_s": 0.2}
    fila.colher_e_zerar()  # zera resíduo de outros testes antes de medir
    with unittest.mock.patch.object(fila, "configurado", return_value=cfg), \
         unittest.mock.patch.object(fila, "medir", return_value=_RECURSOS_OK):
        with fila.vaga(db=None):
            pass  # admitida 1: entra e sai limpo

        # a de fora ocupa a única vaga; a de dentro estoura o timeout e é rejeitada
        with fila.vaga(db=None), pytest.raises(fila.FilaEsgotada), fila.vaga(db=None):
            pass

    amostra = fila.colher_e_zerar()
    assert amostra["admitidas"] == 2  # a isolada + a que segurou a vaga
    assert amostra["rejeitadas"] == 1  # a que tentou entrar com a vaga ocupada
    assert amostra["espera_media_ms"] is not None


def test_rota_admin_fila_ciclo_real():
    app.dependency_overrides[apenas_superadmin] = _admin_falso
    try:
        with TestClient(app) as client:
            r = client.get("/api/v1/admin/fila")
            assert r.status_code == 200
            assert r.json()["max_concorrente"] >= 1

            r2 = client.post("/api/v1/admin/fila", json={
                "max_concorrente": 7, "cpu_pct_max": 80, "mem_pct_max": 80,
                "disco_pct_max": 80, "timeout_espera_s": 45,
            })
            assert r2.status_code == 200
            assert r2.json()["max_concorrente"] == 7

            r3 = client.get("/api/v1/admin/fila")
            assert r3.json()["max_concorrente"] == 7

            r4 = client.get("/api/v1/admin/fila/historico?dias=1")
            assert r4.status_code == 200
            assert isinstance(r4.json(), list)
    finally:
        app.dependency_overrides.pop(apenas_superadmin, None)


def test_rota_admin_fila_401_sem_sessao():
    with TestClient(app) as client:
        r = client.get("/api/v1/admin/fila")
    assert r.status_code == 401
