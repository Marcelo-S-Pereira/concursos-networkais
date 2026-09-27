"""[170]: registro de uso por usuário e por ferramenta, na unidade da API.

O que precisa estar certo:
- todo registro sai atribuído à pessoa, à ferramenta e à AÇÃO, sem cada chamada
  precisar repassar isso (contexto por requisição);
- Chat de estudo e Tutor IA, que usam as mesmas funções de IA, saem separados;
- o Tempo real grava STT (segundos), LLM (tokens exatos do stream) e TTS
  (caracteres) — antes não gravava nada;
- o guardrail em US$ passa a contar transcrição e voz;
- o relatório é JUSTO: ação que falhou não conta como ação, o custo dela continua
  somado, e as distribuições que orientam o limite são só de clientes.
"""

import base64
import contextvars
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from starlette.middleware.sessions import SessionMiddleware

from app.api.deps import usuario_atual
from app.core.config import get_settings
from app.core.crypto import cifrar_ia
from app.db.models import AiCallLog, AiConnection, AiPlatform, ChatMessage, Conversation, User
from app.db.session import SessionLocal
from app.main import app
from app.modules.ai_registry import cliente, consumo, orcamento, resolver, servico, uso


def _usuario(db, sufixo: str, *, vitalicio: bool = False) -> int:
    u = User(nome=f"U {sufixo}", email=f"t_uso{sufixo}@teste_test.local", cpf_cifrado="x",
             cpf_indice=f"idx_uso_{sufixo}", telefone="x", role="aluno", vitalicio=vitalicio)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u.id


def _limpar_usuarios(*uids: int) -> None:
    db = SessionLocal()
    for uid in uids:
        db.query(AiCallLog).filter(AiCallLog.user_id == uid).delete()
        conv_ids = [c.id for c in db.query(Conversation).filter(Conversation.user_id == uid)]
        if conv_ids:
            db.query(ChatMessage).filter(ChatMessage.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
            db.query(Conversation).filter(Conversation.id.in_(conv_ids)).delete(synchronize_session=False)
        obj = db.get(User, uid)
        if obj:
            db.delete(obj)
    db.commit()
    db.close()


@pytest.fixture
def conexoes():
    """Uma conexão de texto, uma de transcrição e uma de voz numa plataforma mock.
    Apaga só o que criou, pelo id (lição [034])."""
    db = SessionLocal()
    p = AiPlatform(titulo="MockUso", endpoint="https://mock.local/v1", api_key_cifrada=cifrar_ia("k"))
    db.add(p)
    db.flush()
    llm = AiConnection(platform_id=p.id, nome="Mock LLM", modelo="mock/llm", categoria="texto", ativa=True)
    stt = AiConnection(platform_id=p.id, nome="Mock STT", modelo="mock/stt", categoria="transcricao", ativa=True)
    tts = AiConnection(platform_id=p.id, nome="Mock TTS", modelo="mock/tts", categoria="voz", ativa=True)
    db.add_all([llm, stt, tts])
    db.commit()
    for c in (llm, stt, tts):
        db.refresh(c)
    resolver.invalidar_cache()
    yield llm, stt, tts
    ids = [llm.id, stt.id, tts.id]
    db.query(AiCallLog).filter(AiCallLog.connection_id.in_(ids)).delete(synchronize_session=False)
    db.query(AiConnection).filter(AiConnection.id.in_(ids)).delete(synchronize_session=False)
    db.query(AiPlatform).filter(AiPlatform.id == p.id).delete()
    db.commit()
    db.close()
    resolver.invalidar_cache()


PRECOS = {
    "mock/llm": {"input": 1.0, "output": 2.0},
    "mock/stt": {"por_minuto": 0.006, "input": 0.0, "output": 0.0},
    "mock/tts": {"input": 4.0, "output": 0.0},
}


# --- contexto: quem, qual ferramenta, qual ação ---

def test_registrar_herda_o_contexto_e_o_que_e_explicito_vence():
    db = SessionLocal()
    uid = _usuario(db, "ctx")
    try:
        def dentro():
            uso.marcar(user_id=uid, ferramenta="tutor_ia", conversation_id=77)
            base = dict(connection_id=None, modelo="m", sucesso=True, latencia_ms=1)
            uso.registrar(db, categoria="texto", origem="chat_texto", **base)
            uso.registrar(db, categoria="texto", origem="chat_texto", ferramenta="gemeas", **base)

        contextvars.copy_context().run(dentro)
        a, b = db.query(AiCallLog).filter(AiCallLog.user_id == uid).order_by(AiCallLog.id).all()
        assert (a.ferramenta, a.conversation_id) == ("tutor_ia", 77)
        assert b.ferramenta == "gemeas", "parâmetro explícito vence o contexto"
    finally:
        db.close()
        _limpar_usuarios(uid)


def test_sem_contexto_a_ferramenta_cai_na_origem_e_chat_nao_e_chutado():
    db = SessionLocal()
    uid = _usuario(db, "orig")
    try:
        def dentro():
            base = dict(connection_id=None, modelo="m", sucesso=True, latencia_ms=1, user_id=uid)
            uso.registrar(db, categoria="texto", origem="gemeas", **base)
            uso.registrar(db, categoria="texto", origem="tutor_explica", **base)
            uso.registrar(db, categoria="texto", origem="chat_texto", **base)

        contextvars.copy_context().run(dentro)
        linhas = {r.origem: r.ferramenta for r in db.query(AiCallLog).filter(AiCallLog.user_id == uid)}
        assert linhas["gemeas"] == "gemeas"
        assert linhas["tutor_explica"] == "simulado_tutor"
        # Chat de estudo e Tutor IA usam a mesma origem: sem a rota marcar, NÃO se chuta
        assert linhas["chat_texto"] is None
    finally:
        db.close()
        _limpar_usuarios(uid)


def test_middleware_abre_contexto_com_o_usuario_da_sessao_e_acao_nova_por_requisicao():
    mini = FastAPI()
    mini.add_middleware(uso.UsoContextoMiddleware)
    mini.add_middleware(SessionMiddleware, secret_key="segredo-de-teste")

    @mini.get("/login")
    def login(request: Request):
        request.session["user_id"] = 7
        return {"ok": True}

    @mini.get("/ctx")
    def ctx():
        uso.marcar(ferramenta="chat_estudo")  # não pode vazar para a próxima requisição
        return uso.contexto_atual()

    with TestClient(mini) as c:
        c.get("/login")
        r1 = c.get("/ctx").json()
        r2 = c.get("/ctx").json()
    assert r1["user_id"] == 7 and r2["user_id"] == 7
    assert r1["acao_id"] != r2["acao_id"], "cada requisição é uma ação nova"
    assert "ferramenta" not in uso.contexto_atual(), "a marca da rota não vaza para fora da requisição"


# --- rotas do chat: Chat de estudo x Tutor IA, e uma ação agrupa STT/LLM/TTS ---

def test_chat_separa_chat_estudo_de_tutor_ia_e_agrupa_a_acao(conexoes, monkeypatch):
    llm, _, tts = conexoes
    monkeypatch.setattr(servico, "chamar_chat",
                        lambda conn, msgs, max_tokens=None: ("Resposta.", {"prompt_tokens": 30, "completion_tokens": 5,
                                                                            "total_tokens": 35}))
    monkeypatch.setattr(cliente, "falar", lambda conn, texto, voz: b"audio")
    monkeypatch.setattr("app.modules.chat.chat.contexto_biblioteca", lambda *a, **k: "")
    monkeypatch.setattr("app.modules.ai_registry.precos.precos_da_plataforma", lambda plat: {})

    db = SessionLocal()
    uid = _usuario(db, "chat", vitalicio=True)
    c_chat = Conversation(user_id=uid, titulo="c", modo="chat")
    c_tutor = Conversation(user_id=uid, titulo="t", modo="tutor")
    db.add_all([c_chat, c_tutor])
    db.commit()
    ids = {"chat": c_chat.id, "tutor": c_tutor.id}
    db.close()

    app.dependency_overrides[usuario_atual] = lambda: SessionLocal().get(User, uid)
    try:
        with TestClient(app) as client:
            for cid in ids.values():
                r = client.post(f"/api/v1/chat/conversas/{cid}/mensagem-falada", json={"texto": "oi"})
                assert r.status_code == 200, r.text

        db = SessionLocal()
        linhas = db.query(AiCallLog).filter(AiCallLog.user_id == uid).order_by(AiCallLog.id).all()
        por_conversa = {ids["chat"]: "chat_estudo", ids["tutor"]: "tutor_ia"}
        assert len(linhas) == 4, "2 ações × (texto + voz)"
        for r in linhas:
            assert r.ferramenta == por_conversa[r.conversation_id], (r.origem, r.ferramenta)
        acoes = {}
        for r in linhas:
            acoes.setdefault(r.conversation_id, set()).add(r.acao_id)
        assert all(len(v) == 1 and None not in v for v in acoes.values()), "texto+voz da mesma mensagem = 1 ação"
        assert acoes[ids["chat"]] != acoes[ids["tutor"]]
        db.close()
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar_usuarios(uid)


# --- Tempo real: antes não gravava nada ---

def test_tempo_real_grava_stt_llm_e_tts_na_unidade_da_api(conexoes, monkeypatch):
    llm, stt, tts = conexoes

    class STTFalso:
        def __init__(self, conn, idioma="pt"):
            pass

        async def conectar(self):
            pass

        async def mandar_audio(self, pcm):
            pass

        async def commit(self):
            pass

        async def eventos(self):
            yield {"type": "conversation.item.input_audio_transcription.completed", "transcript": "olá, tudo bem?"}

        async def fechar(self):
            pass

    async def llm_falso(conn, mensagens, *, max_tokens=None, usage_out=None):
        if usage_out is not None:
            usage_out.update({"prompt_tokens": 50, "completion_tokens": 7, "total_tokens": 57})
        yield "Tudo bem. "
        yield "E você?"

    async def tts_falso(conn, texto, voz):
        yield b"\x00\x01" * 8

    monkeypatch.setattr("app.api.ws_voz.SessaoSTT", STTFalso)
    monkeypatch.setattr("app.api.ws_voz.chamar_chat_streaming", llm_falso)
    monkeypatch.setattr("app.api.ws_voz.falar_streaming", tts_falso)
    monkeypatch.setattr("app.api.ws_voz.contexto_biblioteca", lambda *a, **k: "")

    db = SessionLocal()
    uid = _usuario(db, "ws", vitalicio=True)
    conversa = Conversation(user_id=uid, titulo="rt", modo="tutor")
    db.add(conversa)
    db.commit()
    cid = conversa.id
    db.close()

    sessao = base64.b64encode(json.dumps({"user_id": uid}).encode())
    cookie = TimestampSigner(str(get_settings().session_secret_key)).sign(sessao).decode()
    try:
        with TestClient(app) as client, client.websocket_connect(
            f"/ws/tutor-voz?conversation_id={cid}", headers={"cookie": f"concursos_sessao={cookie}"},
        ) as ws:
            ws.send_bytes(b"\x00" * 64000)  # 2 s de PCM16 16 kHz mono
            ws.send_text(json.dumps({"type": "commit"}))
            while True:
                msg = ws.receive()
                if msg.get("text") and json.loads(msg["text"]).get("type") == "response_done":
                    break
            ws.send_text(json.dumps({"type": "stop"}))

        db = SessionLocal()
        linhas = {r.origem: r for r in db.query(AiCallLog).filter(AiCallLog.user_id == uid)}
        assert set(linhas) == {"tutor_voz_stt", "tutor_voz_llm", "tutor_voz_tts"}, list(linhas)
        assert (linhas["tutor_voz_stt"].unidades, linhas["tutor_voz_stt"].tipo_unidade) == (2, "segundos")
        assert linhas["tutor_voz_llm"].prompt_tokens == 50 and linhas["tutor_voz_llm"].completion_tokens == 7
        assert linhas["tutor_voz_tts"].unidades == len("Tudo bem.") + len("E você?")
        assert linhas["tutor_voz_tts"].tipo_unidade == "caracteres"
        for r in linhas.values():
            assert r.ferramenta == "tutor_ia_tempo_real" and r.conversation_id == cid and r.sucesso, r.origem
        assert len({r.acao_id for r in linhas.values()}) == 1, "STT+LLM+TTS do turno = uma ação"
        db.close()
    finally:
        _limpar_usuarios(uid)


# --- custo: guardrail e relatório ---

def test_guardrail_em_dolar_passa_a_contar_transcricao_e_voz(conexoes, monkeypatch):
    llm, stt, tts = conexoes
    monkeypatch.setattr("app.modules.ai_registry.precos.precos_da_plataforma", lambda plat: PRECOS)
    db = SessionLocal()
    desde = datetime.now(UTC) - timedelta(minutes=1)
    antes = orcamento.gasto_usd(db, desde)
    try:
        def linha(conn, categoria, **kw):
            return AiCallLog(connection_id=conn.id, categoria=categoria, origem="teste_guardrail", modelo="m",
                             sucesso=True, latencia_ms=1, **kw)

        db.add_all([
            linha(stt, "transcricao", unidades=120, tipo_unidade="segundos"),
            linha(tts, "voz", unidades=250_000, tipo_unidade="caracteres"),
            linha(llm, "texto", prompt_tokens=100_000, completion_tokens=10_000),
        ])
        db.commit()
        # STT 2 min × 0,006 = 0,012 · TTS 250 mil chars × 4/1M = 1,0 · LLM 0,1 + 0,02
        assert orcamento.gasto_usd(db, desde) - antes == pytest.approx(0.012 + 1.0 + 0.12, abs=1e-6)
    finally:
        db.close()


def test_relatorio_justo_falha_nao_e_acao_historico_nao_vira_acao_e_distribuicao_so_de_clientes(conexoes, monkeypatch):
    llm, stt, tts = conexoes
    monkeypatch.setattr("app.modules.ai_registry.consumo.precos_da_plataforma", lambda plat: PRECOS)
    db = SessionLocal()
    cli = _usuario(db, "rel_c")
    vit = _usuario(db, "rel_v", vitalicio=True)
    try:
        def linha(uid, conn, cat, acao, ok=True, ferr="tutor_ia", **kw):
            return AiCallLog(user_id=uid, connection_id=conn.id, categoria=cat, origem="t", modelo=conn.modelo,
                             sucesso=ok, latencia_ms=1, ferramenta=ferr, acao_id=acao, **kw)

        db.add_all([
            # ação A do cliente (válida): STT 60 s + LLM + TTS = 0,006 + 0,12 + 0,2
            linha(cli, stt, "transcricao", "A", unidades=60, tipo_unidade="segundos"),
            linha(cli, llm, "texto", "A", prompt_tokens=100_000, completion_tokens=10_000),
            linha(cli, tts, "voz", "A", unidades=50_000, tipo_unidade="caracteres"),
            # ação B do cliente: o LLM FALHOU — não conta como ação, mas o custo (0,1) é real
            linha(cli, llm, "texto", "B", ok=False, prompt_tokens=100_000),
            # histórico sem ação nem ferramenta: entra no custo, NÃO vira ação
            linha(cli, llm, "texto", None, ferr=None, prompt_tokens=100_000),
            # ação do vitalício: aparece, mas fica fora da distribuição dos clientes
            linha(vit, llm, "texto", "C", prompt_tokens=1_000_000),
        ])
        db.commit()

        r = consumo.resumo(db, 7)
        u = {x["user_id"]: x for x in r["usuarios"]}
        c = u[cli]
        assert c["sem_limites"] is False and u[vit]["sem_limites"] is True
        assert c["total"]["custo"]["usd"] == pytest.approx(0.006 + 0.12 + 0.2 + 0.1 + 0.1, abs=1e-6)
        assert c["total"]["falhas"] == 1
        tutor = next(f for f in c["por_ferramenta"] if f["ferramenta"] == "tutor_ia")
        assert tutor["acoes"] == 1, "só a ação A vale; a B falhou"
        hist = next(f for f in c["por_ferramenta"] if f["ferramenta"] == "sem_ferramenta")
        assert hist["acoes"] == 0, "sem acao_id não dá para saber quantas ações foram — não invento"
        # a distribuição de custo por ação é só de clientes: a ação C (US$ 1,0) do vitalício não entra
        tf = next(f for f in r["ferramentas"] if f["ferramenta"] == "tutor_ia")
        assert tf["custo_por_acao_clientes"]["max"]["usd"] < 0.5
        assert r["distribuicao_clientes"]["usuarios_com_uso"] >= 1
    finally:
        db.close()
        _limpar_usuarios(cli, vit)


def test_falha_ao_buscar_preco_e_lembrada_e_nao_repete_a_cada_chamada(conexoes, monkeypatch):
    """O teto de orçamento consulta os preços em TODA chamada de IA; sem lembrar a
    falha, um `/models` lento do provedor atrasava o app inteiro (até 20 s cada)."""
    from app.modules.ai_registry import precos

    llm, _, _ = conexoes
    plat = llm.plataforma
    chamadas = []

    def falha(*a, **k):
        chamadas.append(1)
        raise RuntimeError("sem rede")

    monkeypatch.setattr(precos.httpx, "get", falha)
    precos._cache.pop(plat.id, None)
    assert precos.precos_da_plataforma(plat) == {}
    assert precos.precos_da_plataforma(plat) == {}
    assert len(chamadas) == 1, "a segunda chamada não deveria tentar a rede de novo"
    precos._cache.pop(plat.id, None)


def test_rota_admin_uso_resumo_so_para_o_dono_e_devolve_a_estrutura(monkeypatch):
    from app.api.deps import apenas_superadmin

    monkeypatch.setattr("app.modules.ai_registry.consumo.usd_brl", lambda: (5.0, "teste"))
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/uso/resumo").status_code == 401  # sem sessão

        app.dependency_overrides[apenas_superadmin] = lambda: SessionLocal().query(User).first()
        try:
            r = client.get("/api/v1/admin/uso/resumo?dias=7")
        finally:
            app.dependency_overrides.pop(apenas_superadmin, None)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert {"dias", "cotacao", "total", "ferramentas", "usuarios", "distribuicao_clientes", "notas"} <= set(corpo)
    assert corpo["cotacao"] == {"usd_brl": 5.0, "fonte": "teste"}
