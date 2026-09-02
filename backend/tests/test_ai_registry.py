import httpx
import pytest

from app.db.models import AiConnection
from app.db.session import SessionLocal
from app.modules.ai_registry import cliente, resolver, servico


@pytest.fixture
def conexao_texto():
    db = SessionLocal()
    from app.core.crypto import cifrar_ia
    db.query(AiConnection).delete()
    c = AiConnection(nome="Mock", endpoint="https://mock.local/v1", api_key_cifrada=cifrar_ia("k-test"),
                     modelo="mock-model", categoria="texto", ativa=True)
    db.add(c)
    db.commit()
    db.refresh(c)
    resolver.invalidar_cache()
    yield db, c
    db.query(AiConnection).delete()
    db.commit()
    db.close()
    resolver.invalidar_cache()


def test_resolver_devolve_ativa(conexao_texto):
    db, c = conexao_texto
    cadeia = resolver.cadeia_para_categoria(db, "texto")
    assert [x.id for x in cadeia] == [c.id]


def test_sem_conexao_erro_claro(conexao_texto):
    db, _ = conexao_texto
    with pytest.raises(servico.SemConexaoIA):
        servico.conversar(db, "visao", [{"role": "user", "content": "oi"}], origem="teste")


def test_conversar_chama_provider_e_loga(conexao_texto, monkeypatch):
    db, c = conexao_texto

    def fake_post(url, headers, json, timeout):
        assert url.endswith("/chat/completions")
        assert headers["Authorization"] == "Bearer k-test"  # decifrou certo
        req = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "resposta ok"}}],
                  "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}},
            request=req,
        )

    monkeypatch.setattr(cliente.httpx, "post", fake_post)
    out = servico.conversar(db, "texto", [{"role": "user", "content": "explique"}], origem="teste")
    assert out == "resposta ok"
    from app.db.models import AiCallLog
    log = db.query(AiCallLog).order_by(AiCallLog.id.desc()).first()
    assert log.sucesso and log.total_tokens == 8 and log.connection_id == c.id


def test_resposta_vazia_vira_erro_com_usage(conexao_texto, monkeypatch):
    db, _ = conexao_texto

    def fake_post(url, headers, json, timeout):
        req = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": ""}}],
                  "usage": {"prompt_tokens": 10, "completion_tokens": 4000}},
            request=req,
        )

    monkeypatch.setattr(cliente.httpx, "post", fake_post)
    with pytest.raises(cliente.AiCallError) as ei:
        cliente.chamar_chat(db.query(AiConnection).first(), [{"role": "user", "content": "x"}])
    assert ei.value.usage["completion_tokens"] == 4000
