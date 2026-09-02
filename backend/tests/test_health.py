from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_publico_nao_vaza_versao():
    """Health é público, mas número de versão é reconhecimento de alvo.

    Sem sessão, a resposta diz apenas que o sistema está vivo.
    """
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    corpo = res.json()
    assert corpo["status"] == "ok"
    assert "pgvector" not in corpo
    assert "database" not in corpo
