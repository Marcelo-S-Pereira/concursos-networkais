"""[123]: o Tutor IA precisa SEMPRE saber o que está carregado na conversa,
mesmo antes de qualquer pergunta específica (a busca semântica sozinha falha
pra saudação genérica, "Olá!" não recupera nada relevante) — e o modo carro
precisa falar de volta mesmo quando o aluno digita em vez de usar o
microfone. Chamadas reais à Together já validadas manualmente (ver Registro
de Atividades [123]); aqui trava o comportamento com mock, rápido e sem
custo de API a cada `pytest`."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import usuario_atual
from app.core.crypto import cifrar_ia
from app.db.models import AiCallLog, AiConnection, AiPlatform, ChatMessage, Conversation, RagDocument, User
from app.db.session import SessionLocal
from app.main import app
from app.modules.ai_registry import resolver
from app.modules.chat.chat import _material_selecionado


@pytest.fixture
def doc_tutor():
    """Um documento classificado uso_tutor, com descrição — pra testar que o
    material entra no prompt mesmo sem nenhuma busca semântica acontecer."""
    db = SessionLocal()
    d = RagDocument(titulo="apostila-teste.pdf", descricao="Resumo de teste sobre segurança da informação.",
                    uso_tutor=True, chunk_count=0)
    db.add(d)
    db.commit()
    db.refresh(d)
    yield db, d
    db.query(RagDocument).filter(RagDocument.id == d.id).delete()
    db.commit()
    db.close()


def test_material_selecionado_monta_bloco_com_titulo_e_descricao(doc_tutor):
    db, d = doc_tutor
    conversa = Conversation(user_id=1, modo="tutor", persona="professor", rag_doc_ids=[d.id])
    bloco = _material_selecionado(db, conversa)
    assert "MATERIAL DESTA CONVERSA" in bloco
    assert d.titulo in bloco
    assert d.descricao in bloco


def test_material_selecionado_vazio_sem_doc_ids(doc_tutor):
    db, _ = doc_tutor
    conversa = Conversation(user_id=1, modo="tutor", persona="professor", rag_doc_ids=[])
    assert _material_selecionado(db, conversa) == ""


def test_material_selecionado_vazio_no_modo_chat(doc_tutor):
    db, d = doc_tutor
    conversa = Conversation(user_id=1, modo="chat", persona="professor", rag_doc_ids=[d.id])
    assert _material_selecionado(db, conversa) == ""


def test_material_selecionado_sem_descricao_ainda(doc_tutor):
    db, d = doc_tutor
    d.descricao = ""
    db.commit()
    conversa = Conversation(user_id=1, modo="tutor", persona="professor", rag_doc_ids=[d.id])
    bloco = _material_selecionado(db, conversa)
    assert "ainda sem resumo" in bloco


# --- rota /mensagem-falada: mesma resposta de texto, mas TAMBÉM fala ---

def test_rota_mensagem_falada_ponta_a_ponta(monkeypatch):
    db = SessionLocal()
    admin = User(nome="Admin Teste", email="admin@falada_rota_test.local", cpf_cifrado="x",
                cpf_indice="idx_falada_rota_test", telefone="x", role="superadmin")
    db.add(admin)
    db.commit()
    db.refresh(admin)
    app.dependency_overrides[usuario_atual] = lambda: admin

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

    conversa = Conversation(user_id=admin.id, modo="tutor", persona="amigo", titulo="Nova conversa")
    db.add(conversa)
    db.commit()
    db.refresh(conversa)
    cid = conversa.id

    def fake_post(url, headers=None, files=None, data=None, json=None, timeout=None):
        if url.endswith("/chat/completions"):
            resp = {"choices": [{"message": {"content": "Uma variável guarda um valor na memória."}}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18}}
            return httpx.Response(200, json=resp, request=httpx.Request("POST", url))
        if url.endswith("/audio/speech"):
            return httpx.Response(200, content=b"audio-falado-fake", request=httpx.Request("POST", url))
        raise AssertionError(f"URL inesperada: {url}")

    monkeypatch.setattr(httpx, "post", fake_post)
    try:
        with TestClient(app) as client:
            r = client.post(f"/api/v1/chat/conversas/{cid}/mensagem-falada",
                            json={"texto": "O que é uma variável?"})
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["resposta"] == "Uma variável guarda um valor na memória."
        assert corpo["audio_b64"]  # o texto digitado TAMBÉM veio falado

        salvas = db.query(ChatMessage).filter(ChatMessage.conversation_id == cid).order_by(ChatMessage.id).all()
        assert len(salvas) == 2
        assert salvas[0].role == "user" and salvas[0].conteudo == "O que é uma variável?"
        assert salvas[1].role == "assistant" and salvas[1].conteudo == "Uma variável guarda um valor na memória."
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        db.query(ChatMessage).filter(ChatMessage.conversation_id == cid).delete()
        db.query(Conversation).filter(Conversation.id == cid).delete()
        ids = [texto_conn.id, tts_conn.id]
        db.query(AiCallLog).filter(AiCallLog.connection_id.in_(ids)).delete(synchronize_session=False)
        db.query(AiConnection).filter(AiConnection.id.in_(ids)).delete(synchronize_session=False)
        db.query(AiPlatform).filter(AiPlatform.id == p.id).delete()
        db.query(User).filter(User.id == admin.id).delete()
        db.commit()
        resolver.invalidar_cache()


def test_rota_mensagem_falada_texto_vazio_da_422():
    db = SessionLocal()
    admin = User(nome="Admin Teste2", email="admin2@falada_rota_test.local", cpf_cifrado="x",
                cpf_indice="idx_falada_rota_test2", telefone="x", role="superadmin")
    db.add(admin)
    db.commit()
    db.refresh(admin)
    app.dependency_overrides[usuario_atual] = lambda: admin
    conversa = Conversation(user_id=admin.id, modo="tutor", persona="professor", titulo="Nova conversa")
    db.add(conversa)
    db.commit()
    db.refresh(conversa)
    cid = conversa.id
    try:
        with TestClient(app) as client:
            r = client.post(f"/api/v1/chat/conversas/{cid}/mensagem-falada", json={"texto": "   "})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        db.query(Conversation).filter(Conversation.id == cid).delete()
        db.query(User).filter(User.id == admin.id).delete()
        db.commit()
