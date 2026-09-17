"""Chat por voz: STT (transcrever) e TTS (falar). Chamadas reais à Together já
foram validadas manualmente (loop fechado TTS->STT batendo com o texto
original, ver Registro de Atividades [095]) — aqui trava o COMPORTAMENTO com
httpx mockado, rápido e determinístico, sem gastar API a cada `pytest`."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import usuario_atual
from app.core.crypto import cifrar_ia
from app.db.models import AiCallLog, AiConnection, AiPlatform, ChatMessage, Conversation, User
from app.db.session import SessionLocal
from app.main import app
from app.modules.ai_registry import cliente, resolver, servico
from app.modules.ai_registry.cliente import AiCallError


@pytest.fixture
def conexoes_voz():
    """Uma conexão de transcrição (STT) e uma de voz (TTS), na mesma
    plataforma mock. Apaga só o que criou, pelo id (lição [034])."""
    db = SessionLocal()
    p = AiPlatform(titulo="Mock", endpoint="https://mock.local/v1", api_key_cifrada=cifrar_ia("k-test"))
    db.add(p)
    db.flush()
    stt = AiConnection(platform_id=p.id, nome="Mock STT", modelo="openai/whisper-large-v3",
                       categoria="transcricao", ativa=True)
    tts = AiConnection(platform_id=p.id, nome="Mock TTS", modelo="hexgrad/Kokoro-82M",
                       categoria="voz", ativa=True)
    db.add_all([stt, tts])
    db.commit()
    db.refresh(stt)
    db.refresh(tts)
    resolver.invalidar_cache()
    yield db, stt, tts
    db.query(AiCallLog).filter(AiCallLog.connection_id.in_([stt.id, tts.id])).delete(synchronize_session=False)
    db.query(AiConnection).filter(AiConnection.id.in_([stt.id, tts.id])).delete(synchronize_session=False)
    db.query(AiPlatform).filter(AiPlatform.id == p.id).delete()
    db.commit()
    db.close()
    resolver.invalidar_cache()


# --- cliente.py: contrato da API (mockado) ---

def test_transcrever_parseia_verbose_json(conexoes_voz, monkeypatch):
    _, stt, _ = conexoes_voz

    def fake_post(url, headers=None, files=None, data=None, json=None, timeout=None):
        assert url.endswith("/audio/transcriptions")
        assert files["file"][0] == "audio.webm"
        assert data["model"] == "openai/whisper-large-v3"
        assert data["language"] == "pt"
        return httpx.Response(200, json={"text": "olá mundo", "duration": 3.7},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    r = cliente.transcrever(stt, b"fake-audio-bytes", "audio.webm")
    assert r == {"texto": "olá mundo", "duracao_s": 3.7}


def test_transcrever_texto_vazio_vira_erro(conexoes_voz, monkeypatch):
    _, stt, _ = conexoes_voz

    def fake_post(url, headers=None, files=None, data=None, json=None, timeout=None):
        return httpx.Response(200, json={"text": "  "}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(AiCallError):
        cliente.transcrever(stt, b"silencio", "audio.webm")


def test_falar_devolve_bytes_do_audio(conexoes_voz, monkeypatch):
    _, _, tts = conexoes_voz
    audio_falso = b"\x00\x01RIFFfake-audio-bytes"

    def fake_post(url, headers=None, files=None, data=None, json=None, timeout=None):
        assert url.endswith("/audio/speech")
        assert json["model"] == "hexgrad/Kokoro-82M"
        assert json["input"] == "teste"
        assert json["voice"] == "pf_dora"
        return httpx.Response(200, content=audio_falso, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    r = cliente.falar(tts, "teste", "pf_dora")
    assert r == audio_falso


# --- servico.py: resolução da cadeia + registro da telemetria (unidades certas) ---

def test_transcrever_audio_loga_em_segundos(conexoes_voz, monkeypatch):
    db, stt, _ = conexoes_voz

    def fake_post(url, headers=None, files=None, data=None, json=None, timeout=None):
        return httpx.Response(200, json={"text": "resposta da questão trinta e três", "duration": 4.2},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    resultado = servico.transcrever_audio(db, b"audio", "p.webm", origem="teste")
    assert resultado["texto"] == "resposta da questão trinta e três"

    log = db.query(AiCallLog).filter(AiCallLog.connection_id == stt.id).order_by(AiCallLog.id.desc()).first()
    assert log.categoria == "transcricao"
    assert log.unidades == 4  # int(4.2)
    assert log.tipo_unidade == "segundos"
    assert log.sucesso is True


def test_falar_texto_usa_voz_padrao_do_kokoro_e_loga_em_caracteres(conexoes_voz, monkeypatch):
    db, _, tts = conexoes_voz

    def fake_post(url, headers=None, files=None, data=None, json=None, timeout=None):
        assert json["voice"] == "pf_dora"  # voz padrão em português quando ninguém escolheu
        return httpx.Response(200, content=b"audio-bytes", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    audio = servico.falar_texto(db, "resposta com dez caracteres", origem="teste")
    assert audio == b"audio-bytes"

    log = db.query(AiCallLog).filter(AiCallLog.connection_id == tts.id).order_by(AiCallLog.id.desc()).first()
    assert log.categoria == "voz"
    assert log.unidades == len("resposta com dez caracteres")
    assert log.tipo_unidade == "caracteres"


def test_sem_conexao_de_voz_erro_claro(conexoes_voz):
    db, stt, tts = conexoes_voz
    db.delete(tts)
    db.commit()
    resolver.invalidar_cache()
    with pytest.raises(servico.SemConexaoIA):
        servico.falar_texto(db, "oi", origem="teste")


# --- rota HTTP real (TestClient): prova que File/Form chegam certo na função,
# não só que a lógica interna funciona isolada. ---

def test_rota_audio_ponta_a_ponta(conexoes_voz, monkeypatch):
    db, stt, tts = conexoes_voz
    admin = User(nome="Admin Teste", email="admin@voz_rota_test.local", cpf_cifrado="x",
                cpf_indice="idx_voz_rota_test", telefone="x", role="superadmin")
    db.add(admin)
    db.commit()
    db.refresh(admin)
    app.dependency_overrides[usuario_atual] = lambda: admin

    texto_conn = AiConnection(platform_id=stt.platform_id, nome="Mock LLM", modelo="mock-llm",
                              categoria="texto", ativa=True)
    db.add(texto_conn)
    db.commit()
    db.refresh(texto_conn)
    resolver.invalidar_cache()

    conversa = Conversation(user_id=admin.id, exam_id=None, titulo="Nova conversa")
    db.add(conversa)
    db.commit()
    db.refresh(conversa)
    cid = conversa.id

    def fake_post(url, headers=None, files=None, data=None, json=None, timeout=None):
        if url.endswith("/audio/transcriptions"):
            return httpx.Response(200, json={"text": "o que é energia cinética?", "duration": 2.5},
                                  request=httpx.Request("POST", url))
        if url.endswith("/audio/speech"):
            return httpx.Response(200, content=b"audio-de-resposta-fake", request=httpx.Request("POST", url))
        if url.endswith("/chat/completions"):
            resp = {"choices": [{"message": {"content": "Energia cinética é a energia do movimento."}}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18}}
            return httpx.Response(200, json=resp, request=httpx.Request("POST", url))
        raise AssertionError(f"URL inesperada: {url}")

    monkeypatch.setattr(httpx, "post", fake_post)
    try:
        with TestClient(app) as client:
            r = client.post(f"/api/v1/chat/conversas/{cid}/audio",
                            files={"file": ("pergunta.webm", b"fake-audio-do-aluno", "audio/webm")})
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["transcricao"] == "o que é energia cinética?"
        assert corpo["audio_b64"]  # [133]: URL foi revertida (vazamento via cache CDN) — de volta ao base64

        # persistiu as duas mensagens (user com a transcrição, assistant com a resposta)
        salvas = db.query(ChatMessage).filter(ChatMessage.conversation_id == cid).order_by(ChatMessage.id).all()
        assert len(salvas) == 2
        assert salvas[0].role == "user" and salvas[0].conteudo == "o que é energia cinética?"
        assert salvas[1].role == "assistant"
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        db.query(ChatMessage).filter(ChatMessage.conversation_id == cid).delete()
        db.query(Conversation).filter(Conversation.id == cid).delete()
        db.query(AiCallLog).filter(AiCallLog.connection_id == texto_conn.id).delete()
        db.query(AiConnection).filter(AiConnection.id == texto_conn.id).delete()
        db.query(User).filter(User.id == admin.id).delete()
        db.commit()
        resolver.invalidar_cache()
