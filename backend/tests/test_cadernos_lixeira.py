"""Ciclo da lixeira de cadernos: soft delete, restaurar, exclusão permanente.

Roda pelas rotas HTTP reais (TestClient) no banco de teste isolado. A dependência
de superadmin é sobreposta — os endpoints só usam o usuário para autorizar, então
um usuário falso basta. O caderno de teste é criado e removido pelo id exato.
"""

from fastapi.testclient import TestClient

from app.api.deps import apenas_superadmin, usuario_atual
from app.db.models import Exam, User
from app.db.session import SessionLocal
from app.main import app


def _admin_falso() -> User:
    return User(id=1, nome="Admin Teste", email="admin@lixeira_test.local", role="superadmin")


def test_ciclo_lixeira_do_caderno():
    app.dependency_overrides[apenas_superadmin] = _admin_falso
    app.dependency_overrides[usuario_atual] = _admin_falso

    db = SessionLocal()
    ex = Exam(banca="__t__", orgao="__t__", cargo="__lixeira_test__")
    db.add(ex)
    db.commit()
    db.refresh(ex)
    exam_id = ex.id
    db.close()

    try:
        with TestClient(app) as client:
            # nasce ativo
            assert any(e["id"] == exam_id for e in client.get("/api/v1/exames").json())

            # editar dados mestre
            r = client.patch(f"/api/v1/exames/{exam_id}", json={"banca": "Cesgranrio", "ano": 2023})
            assert r.status_code == 200
            assert r.json()["banca"] == "Cesgranrio" and r.json()["ano"] == 2023

            # excluir = vai para a lixeira (soft), some dos ativos
            assert client.delete(f"/api/v1/exames/{exam_id}").status_code == 204
            assert not any(e["id"] == exam_id for e in client.get("/api/v1/exames").json())
            assert any(e["id"] == exam_id for e in client.get("/api/v1/exames/lixeira").json())

            # restaurar = volta aos ativos, sai da lixeira
            assert client.post(f"/api/v1/exames/{exam_id}/restaurar").status_code == 200
            assert any(e["id"] == exam_id for e in client.get("/api/v1/exames").json())

            # permanente recusa enquanto está ativo (precisa passar pela lixeira)
            assert client.delete(f"/api/v1/exames/{exam_id}/permanente").status_code == 409

            # excluir de novo e então apagar em definitivo
            assert client.delete(f"/api/v1/exames/{exam_id}").status_code == 204
            assert client.delete(f"/api/v1/exames/{exam_id}/permanente").status_code == 204

            # sumiu de vez: nem ativo nem lixeira
            assert not any(e["id"] == exam_id for e in client.get("/api/v1/exames/lixeira").json())
    finally:
        app.dependency_overrides.clear()
        db = SessionLocal()
        obj = db.get(Exam, exam_id)
        if obj:
            db.delete(obj)
            db.commit()
        db.close()
