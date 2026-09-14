"""[125]: catálogo de prompts — a base de dados é a ÚNICA fonte de verdade do
texto enviado à IA e da descrição de cada prompt. Cobre: `buscar()` devolve o
texto real (a suíte semeia as 12 linhas em conftest.py) e lança erro claro
para uma chave inexistente (nunca devolve "" silenciosamente); e o ciclo
admin (listar/editar) pelas rotas HTTP reais."""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import apenas_superadmin
from app.db.models import Prompt, User
from app.db.session import SessionLocal
from app.main import app
from app.modules.prompts import prompts
from app.modules.prompts.seed import PROMPTS


def _admin_falso() -> User:
    return User(id=1, nome="Admin Teste", email="admin@prompts_test.local", role="superadmin")


def test_buscar_devolve_o_texto_real_de_uma_chave_semeada():
    db = SessionLocal()
    chave = PROMPTS[0]["chave"]
    texto = prompts.buscar(db, chave)
    db.close()
    assert texto == PROMPTS[0]["texto"]


def test_buscar_chave_inexistente_lanca_erro_claro_em_vez_de_string_vazia():
    db = SessionLocal()
    with pytest.raises(prompts.PromptNaoEncontrado):
        prompts.buscar(db, "chave_que_nao_existe_de_jeito_nenhum")
    db.close()


def test_rota_listar_devolve_as_12_linhas_com_metadados():
    app.dependency_overrides[apenas_superadmin] = _admin_falso
    try:
        with TestClient(app) as client:
            r = client.get("/api/v1/prompts")
        assert r.status_code == 200
        linhas = r.json()
        assert len(linhas) == len(PROMPTS)
        chaves = {L["chave"] for L in linhas}
        assert chaves == {p["chave"] for p in PROMPTS}
        primeira = next(L for L in linhas if L["chave"] == PROMPTS[0]["chave"])
        assert primeira["nome"] == PROMPTS[0]["nome"]
        assert primeira["onde_usado"] == PROMPTS[0]["onde_usado"]
        assert primeira["como_funciona"] == PROMPTS[0]["como_funciona"]
        assert primeira["texto"] == PROMPTS[0]["texto"]
    finally:
        app.dependency_overrides.pop(apenas_superadmin, None)


def test_rota_editar_muda_o_texto_e_o_proximo_buscar_usa_o_novo():
    app.dependency_overrides[apenas_superadmin] = _admin_falso
    chave = PROMPTS[1]["chave"]
    original = PROMPTS[1]["texto"]
    try:
        with TestClient(app) as client:
            r = client.put(f"/api/v1/prompts/{chave}", json={"texto": "TEXTO EDITADO NO TESTE"})
        assert r.status_code == 200
        assert r.json()["texto"] == "TEXTO EDITADO NO TESTE"

        db = SessionLocal()
        assert prompts.buscar(db, chave) == "TEXTO EDITADO NO TESTE"
        db.close()
    finally:
        # devolve o texto original — este teste não deve deixar o banco de teste alterado
        db = SessionLocal()
        p = db.get(Prompt, chave)
        p.texto = original
        db.commit()
        db.close()
        app.dependency_overrides.pop(apenas_superadmin, None)


def test_rota_editar_recusa_texto_vazio():
    app.dependency_overrides[apenas_superadmin] = _admin_falso
    chave = PROMPTS[2]["chave"]
    try:
        with TestClient(app) as client:
            r = client.put(f"/api/v1/prompts/{chave}", json={"texto": "   "})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(apenas_superadmin, None)


def test_rota_editar_chave_inexistente_da_404():
    app.dependency_overrides[apenas_superadmin] = _admin_falso
    try:
        with TestClient(app) as client:
            r = client.put("/api/v1/prompts/nao_existe", json={"texto": "x"})
        assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(apenas_superadmin, None)


def test_rota_listar_401_sem_sessao():
    with TestClient(app) as client:
        r = client.get("/api/v1/prompts")
    assert r.status_code == 401
