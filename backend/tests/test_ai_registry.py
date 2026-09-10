import httpx
import pytest

from app.db.models import AiCallLog, AiConnection, AiPlatform
from app.db.session import SessionLocal
from app.modules.ai_registry import cliente, resolver, servico


@pytest.fixture
def conexao_texto():
    """Plataforma + modelo de teste. Roda no banco de teste (ver conftest), e
    ainda assim apaga só o que criou, pelo id — nunca `delete()` sem filtro em
    tabela de dados (Registro de Atividades [034])."""
    db = SessionLocal()
    from app.core.crypto import cifrar_ia
    p = AiPlatform(titulo="Mock", endpoint="https://mock.local/v1", api_key_cifrada=cifrar_ia("k-test"))
    db.add(p)
    db.flush()
    c = AiConnection(platform_id=p.id, nome="Mock", modelo="mock-model", categoria="texto", ativa=True)
    db.add(c)
    db.commit()
    db.refresh(c)
    resolver.invalidar_cache()
    yield db, c
    db.query(AiCallLog).filter(AiCallLog.connection_id == c.id).delete()
    db.query(AiConnection).filter(AiConnection.id == c.id).delete()
    db.query(AiPlatform).filter(AiPlatform.id == p.id).delete()
    db.commit()
    db.close()
    resolver.invalidar_cache()


def test_resolver_devolve_ativa(conexao_texto):
    db, c = conexao_texto
    cadeia = resolver.cadeia_para_categoria(db, "texto")
    assert [x.id for x in cadeia] == [c.id]


def test_modelo_escolhido_vai_para_a_frente_da_cadeia(conexao_texto):
    """O aluno escolhe a IA da conversa; a escolha entra na frente e o fallback
    fica atrás. Escolha inválida é ignorada — o padrão da categoria atende."""
    db, c = conexao_texto
    outra = AiConnection(platform_id=c.platform_id, nome="Reserva", modelo="m2",
                         categoria="texto", ativa=False, ordem_fallback=2)
    db.add(outra)
    db.commit()
    db.refresh(outra)
    resolver.invalidar_cache()
    try:
        cadeia = resolver.cadeia_para_categoria(db, "texto")
        assert [x.id for x in cadeia] == [c.id, outra.id]
        # escolher a reserva a traz para a frente, sem perder a outra
        assert [x.id for x in servico._com_escolhida(db, cadeia, "texto", outra.id)] == [outra.id, c.id]
        # id inexistente e id de outra categoria são ignorados
        assert [x.id for x in servico._com_escolhida(db, cadeia, "texto", 999999)] == [c.id, outra.id]
        assert [x.id for x in servico._com_escolhida(db, cadeia, "visao", c.id)] == [c.id, outra.id]
        # sem escolha, nada muda
        assert [x.id for x in servico._com_escolhida(db, cadeia, "texto", None)] == [c.id, outra.id]
    finally:
        db.query(AiConnection).filter(AiConnection.id == outra.id).delete()
        db.commit()
        resolver.invalidar_cache()


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
    log = db.query(AiCallLog).order_by(AiCallLog.id.desc()).first()
    assert log.sucesso and log.total_tokens == 8 and log.connection_id == c.id


def test_resposta_vazia_vira_erro_com_usage(conexao_texto, monkeypatch):
    db, conexao = conexao_texto

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
        conn = db.query(AiConnection).filter(AiConnection.id == conexao.id).one()
        cliente.chamar_chat(conn, [{"role": "user", "content": "x"}])
    assert ei.value.usage["completion_tokens"] == 4000
