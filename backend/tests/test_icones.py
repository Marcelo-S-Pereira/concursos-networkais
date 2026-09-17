"""[128]: escolha do ícone de cada slot — biblioteca ou upload, sem linha =
usa texto padrão. Testado pelas rotas HTTP reais (banco de teste)."""

from fastapi.testclient import TestClient

from app.api.deps import apenas_superadmin, usuario_atual
from app.db.models import User
from app.main import app
from app.modules.icones.catalogo import SLOTS


def _admin_falso() -> User:
    return User(id=1, nome="Admin Teste", email="admin@icones_test.local", role="superadmin")


def test_ciclo_biblioteca_upload_remover():
    app.dependency_overrides[apenas_superadmin] = _admin_falso
    app.dependency_overrides[usuario_atual] = _admin_falso
    slot = next(iter(SLOTS))
    try:
        with TestClient(app) as client:
            # sem escolha ainda: não aparece em /icones
            r = client.get("/api/v1/icones")
            assert r.status_code == 200
            assert slot not in r.json()

            # catálogo admin lista o slot com atual=None
            rc = client.get("/api/v1/icones/admin/catalogo")
            assert rc.status_code == 200
            linha = next(x for x in rc.json() if x["slot"] == slot)
            assert linha["atual"] is None

            # escolhe da biblioteca
            r2 = client.put(f"/api/v1/icones/admin/{slot}", json={"nome_icone": "book-open"})
            assert r2.status_code == 200
            linha2 = next(x for x in r2.json() if x["slot"] == slot)
            assert linha2["atual"] == {"tipo": "biblioteca", "valor": "book-open"}

            # /icones público agora reflete a escolha
            r3 = client.get("/api/v1/icones")
            assert r3.json()[slot] == {"tipo": "biblioteca", "valor": "book-open"}

            # upload real substitui a escolha de biblioteca
            r4 = client.post(
                f"/api/v1/icones/admin/{slot}/upload",
                files={"arquivo": ("meu-icone.png", b"\x89PNG\r\n\x1a\nfakepngbytes", "image/png")},
            )
            assert r4.status_code == 200
            linha4 = next(x for x in r4.json() if x["slot"] == slot)
            assert linha4["atual"]["tipo"] == "upload"

            # o arquivo enviado é servido de verdade
            r5 = client.get(f"/api/v1/icones/arquivo/{slot}")
            assert r5.status_code == 200
            assert r5.content == b"\x89PNG\r\n\x1a\nfakepngbytes"

            # remover volta ao estado sem escolha
            r6 = client.delete(f"/api/v1/icones/admin/{slot}")
            assert r6.status_code == 200
            linha6 = next(x for x in r6.json() if x["slot"] == slot)
            assert linha6["atual"] is None

            r7 = client.get("/api/v1/icones")
            assert slot not in r7.json()
    finally:
        app.dependency_overrides.pop(apenas_superadmin, None)
        app.dependency_overrides.pop(usuario_atual, None)


def test_upload_recusa_formato_nao_suportado():
    app.dependency_overrides[apenas_superadmin] = _admin_falso
    slot = next(iter(SLOTS))
    try:
        with TestClient(app) as client:
            r = client.post(
                f"/api/v1/icones/admin/{slot}/upload",
                files={"arquivo": ("virus.exe", b"conteudo", "application/octet-stream")},
            )
            assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(apenas_superadmin, None)


def test_slot_desconhecido_da_422():
    app.dependency_overrides[apenas_superadmin] = _admin_falso
    try:
        with TestClient(app) as client:
            r = client.put("/api/v1/icones/admin/nao-existe", json={"nome_icone": "book-open"})
            assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(apenas_superadmin, None)


def test_rotas_401_sem_sessao():
    with TestClient(app) as client:
        assert client.get("/api/v1/icones").status_code == 401
        assert client.get("/api/v1/icones/admin/catalogo").status_code == 401
