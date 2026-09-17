"""[151]: escolha de voz do Kokoro por conversa (Chat de estudo e Tutor IA).
Cobre: catálogo, validação, persistência (criar/editar/limpar) e — o que mais
importa — que a voz escolhida REALMENTE chega no payload mandado à Together
em vez do padrão, via `httpx` mockado (rápido, sem gastar API real)."""

import httpx
from fastapi.testclient import TestClient

from app.api.deps import usuario_atual
from app.core.crypto import cifrar_ia
from app.db.models import AiCallLog, AiConnection, AiPlatform, ChatMessage, Conversation, User
from app.db.session import SessionLocal
from app.main import app
from app.modules.ai_registry import resolver


def _usuario(db, sufixo):
    u = User(nome="Teste Voz", email=f"teste.voz.151.{sufixo}@example.com", cpf_cifrado="x",
             cpf_indice=f"idx_voz_151_{sufixo}", telefone="x", role="superadmin")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_catalogo_de_vozes():
    db = SessionLocal()
    u = _usuario(db, "catalogo")
    app.dependency_overrides[usuario_atual] = lambda: u
    try:
        with TestClient(app) as client:
            r = client.get("/api/v1/chat/vozes")
        assert r.status_code == 200
        ids = {v["id"] for v in r.json()}
        assert ids == {"pf_dora", "pm_alex", "pm_santa"}
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        db.query(User).filter(User.id == u.id).delete()
        db.commit()


def test_criar_com_voz_invalida_da_422():
    db = SessionLocal()
    u = _usuario(db, "invalida")
    app.dependency_overrides[usuario_atual] = lambda: u
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/chat/conversas", json={"modo": "tutor", "voz_escolhida": "voz-que-nao-existe"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        db.query(User).filter(User.id == u.id).delete()
        db.commit()


def test_criar_editar_e_limpar_voz_escolhida():
    db = SessionLocal()
    u = _usuario(db, "ciclo")
    app.dependency_overrides[usuario_atual] = lambda: u
    cid = None
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/chat/conversas", json={"modo": "tutor", "voz_escolhida": "pm_santa"})
            assert r.status_code == 201, r.text
            corpo = r.json()
            cid = corpo["id"]
            assert corpo["voz_escolhida"] == "pm_santa"

            r = client.get(f"/api/v1/chat/conversas/{cid}")
            assert r.json()["voz_escolhida"] == "pm_santa"

            r = client.patch(f"/api/v1/chat/conversas/{cid}", json={"voz_escolhida": "pm_alex"})
            assert r.status_code == 200, r.text
            assert r.json()["voz_escolhida"] == "pm_alex"

            r = client.patch(f"/api/v1/chat/conversas/{cid}", json={"limpar_voz": True})
            assert r.status_code == 200, r.text
            assert r.json()["voz_escolhida"] is None
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        if cid:
            db.query(Conversation).filter(Conversation.id == cid).delete()
        db.query(User).filter(User.id == u.id).delete()
        db.commit()


def test_voz_escolhida_chega_de_verdade_no_payload_da_together(monkeypatch):
    """O teste que mais importa: a voz que o aluno ESCOLHEU (não a padrão)
    precisa aparecer no campo `voice` que vai pra Together."""
    db = SessionLocal()
    u = _usuario(db, "payload")
    app.dependency_overrides[usuario_atual] = lambda: u

    p = AiPlatform(titulo="Mock", endpoint="https://mock.local/v1", api_key_cifrada=cifrar_ia("k-test"))
    db.add(p)
    db.flush()
    texto_conn = AiConnection(platform_id=p.id, nome="Mock LLM", modelo="mock-llm", categoria="texto", ativa=True)
    tts_conn = AiConnection(platform_id=p.id, nome="Mock TTS", modelo="hexgrad/Kokoro-82M", categoria="voz", ativa=True)
    db.add_all([texto_conn, tts_conn])
    db.commit()
    db.refresh(texto_conn)
    db.refresh(tts_conn)
    resolver.invalidar_cache()

    conversa = Conversation(user_id=u.id, modo="tutor", persona="professor", titulo="Nova conversa",
                            voz_escolhida="pm_alex")
    db.add(conversa)
    db.commit()
    db.refresh(conversa)
    cid = conversa.id

    voz_recebida = {}

    def fake_post(url, headers=None, files=None, data=None, json=None, timeout=None):
        if url.endswith("/chat/completions"):
            resp = {"choices": [{"message": {"content": "Resposta de teste."}}],
                   "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}}
            return httpx.Response(200, json=resp, request=httpx.Request("POST", url))
        if url.endswith("/audio/speech"):
            voz_recebida["voice"] = json["voice"]
            return httpx.Response(200, content=b"audio-fake", request=httpx.Request("POST", url))
        raise AssertionError(f"URL inesperada: {url}")

    monkeypatch.setattr(httpx, "post", fake_post)
    try:
        with TestClient(app) as client:
            r = client.post(f"/api/v1/chat/conversas/{cid}/mensagem-falada", json={"texto": "Oi"})
        assert r.status_code == 200, r.text
        assert voz_recebida["voice"] == "pm_alex", "a voz ESCOLHIDA não chegou no payload — caiu no padrão"
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        db.query(ChatMessage).filter(ChatMessage.conversation_id == cid).delete()
        db.query(Conversation).filter(Conversation.id == cid).delete()
        ids = [texto_conn.id, tts_conn.id]
        db.query(AiCallLog).filter(AiCallLog.connection_id.in_(ids)).delete(synchronize_session=False)
        db.query(AiConnection).filter(AiConnection.id.in_(ids)).delete(synchronize_session=False)
        db.query(AiPlatform).filter(AiPlatform.id == p.id).delete()
        db.query(User).filter(User.id == u.id).delete()
        db.commit()
        resolver.invalidar_cache()
