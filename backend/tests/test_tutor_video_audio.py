"""[111]: `/tutor/documentos/video-audio` — o caminho que FUNCIONA pra
transcrever vídeo (o navegador do usuário grava o áudio da própria aba; o
download server-side em `/documentos/video` é bloqueado pelo YouTube, [109]).
Chamada real já foi validada manualmente (TTS→upload→transcrição→oEmbed real,
ver Registro de Atividades [111]) — aqui trava o comportamento com httpx
mockado, rápido e sem custo de API a cada `pytest`."""

import httpx
from fastapi.testclient import TestClient

from app.api.deps import usuario_atual
from app.db.models import AiCallLog, AiConnection, AiPlatform, RagChunk, RagDocument, User
from app.db.session import SessionLocal
from app.main import app
from app.modules.creditos.carteira import creditar


def _usuario(sufixo: str) -> User:
    db = SessionLocal()
    u = User(nome="Teste 111", email=f"t_111_{sufixo}@teste_test.local", cpf_cifrado="x",
            cpf_indice=f"idx_111_{sufixo}", telefone="x", role="aluno")
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


def _limpar(uid: int) -> None:
    db = SessionLocal()
    doc_ids = [d.id for d in db.query(RagDocument).filter(RagDocument.enviado_por_user_id == uid)]
    if doc_ids:
        db.query(RagChunk).filter(RagChunk.document_id.in_(doc_ids)).delete(synchronize_session=False)
        db.query(RagDocument).filter(RagDocument.id.in_(doc_ids)).delete(synchronize_session=False)
    from app.db.models import CreditTransaction
    db.query(CreditTransaction).filter(CreditTransaction.user_id == uid).delete()
    db.query(User).filter(User.id == uid).delete()
    db.commit()
    db.close()


def test_sem_credito_barra_antes_de_transcrever():
    u = _usuario("sem_credito")
    app.dependency_overrides[usuario_atual] = lambda: u
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/tutor/documentos/video-audio",
                            files={"file": ("v.mp3", b"audio-fake", "audio/mpeg")},
                            data={"url": "https://youtube.com/watch?v=x"})
        assert r.status_code == 402
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar(u.id)


def test_audio_vazio_da_422():
    u = _usuario("audio_vazio")
    db = SessionLocal()
    creditar(db, u.id, 50, "ajuste", "teste")
    db.close()
    app.dependency_overrides[usuario_atual] = lambda: u
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/tutor/documentos/video-audio",
                            files={"file": ("v.mp3", b"", "audio/mpeg")},
                            data={"url": "https://youtube.com/watch?v=x"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar(u.id)


def test_ponta_a_ponta_com_stt_e_oembed_mockados():
    u = _usuario("ok")
    db = SessionLocal()
    creditar(db, u.id, 50, "ajuste", "teste")
    p = AiPlatform(titulo="Mock", endpoint="https://mock.local/v1", api_key_cifrada="")
    db.add(p)
    db.flush()
    from app.core.crypto import cifrar_ia
    p.api_key_cifrada = cifrar_ia("k-test")
    stt = AiConnection(platform_id=p.id, nome="Mock STT", modelo="openai/whisper-large-v3",
                       categoria="transcricao", ativa=True)
    db.add(stt)
    db.commit()
    db.refresh(stt)
    from app.modules.ai_registry import resolver
    resolver.invalidar_cache()

    def fake_post(url, headers=None, files=None, data=None, json=None, timeout=None):
        assert url.endswith("/audio/transcriptions")
        return httpx.Response(200, json={"text": "conteúdo do vídeo transcrito", "duration": 12.0},
                              request=httpx.Request("POST", url))

    def fake_get(url, params=None, timeout=None):
        assert "oembed" in url
        return httpx.Response(200, json={"title": "Título Real Do Vídeo"}, request=httpx.Request("GET", url))

    import unittest.mock
    app.dependency_overrides[usuario_atual] = lambda: u
    try:
        with unittest.mock.patch.object(httpx, "post", fake_post), \
             unittest.mock.patch.object(httpx, "get", fake_get), TestClient(app) as client:
            r = client.post("/api/v1/tutor/documentos/video-audio",
                            files={"file": ("v.mp3", b"audio-fake-mas-nao-vazio", "audio/mpeg")},
                            data={"url": "https://youtube.com/watch?v=abc"})
        assert r.status_code == 201, r.text
        corpo = r.json()
        assert corpo["titulo"] == "Título Real Do Vídeo"

        doc = SessionLocal().get(RagDocument, corpo["id"])
        assert doc.enviado_por_user_id == u.id
        assert doc.uso_tutor is True
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        db2 = SessionLocal()
        db2.query(AiCallLog).filter(AiCallLog.connection_id == stt.id).delete()
        db2.query(AiConnection).filter(AiConnection.id == stt.id).delete()
        db2.query(AiPlatform).filter(AiPlatform.id == p.id).delete()
        db2.commit()
        db2.close()
        resolver.invalidar_cache()
        _limpar(u.id)
