"""[169]: vitalício não tem limite de uso nenhum.

Caso real que originou isto: um QA vitalício mandou 14 mensagens de voz em 18
minutos e foi barrado pelo limite rolante de ritmo — cada mensagem de voz gera 3
linhas no `ai_call_log` (STT + LLM + TTS), então 14 mensagens = 42 chamadas
contra um teto de 40 por sessão de 5h. O vitalício já era isento da porta
diária de créditos, mas não do limite de ritmo nem da cota de recurso (YouTube):
dois sistemas de controle, duas regras de isenção diferentes.

Quem NÃO é vitalício continua com todas as travas — é o que o outro lado destes
testes prova.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.api.deps import usuario_atual
from app.core.flags import set_flag
from app.db.models import AiCallLog, FeatureGrant, ResourceUsageLog, User
from app.db.session import SessionLocal
from app.main import app
from app.modules.ai_registry import limites
from app.modules.features import features

FEATURE = "youtube_videos"


def _criar(db, sufixo: str, *, role: str = "aluno", vitalicio: bool = False) -> int:
    u = User(nome="V", email=f"t_vit{sufixo}@teste_test.local", cpf_cifrado="x",
             cpf_indice=f"idx_vit_{sufixo}", telefone="x", role=role, vitalicio=vitalicio)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u.id


def _limpar(*uids: int) -> None:
    db = SessionLocal()
    for uid in uids:
        db.query(AiCallLog).filter(AiCallLog.user_id == uid).delete()
        db.query(ResourceUsageLog).filter(ResourceUsageLog.user_id == uid).delete()
        db.query(FeatureGrant).filter(FeatureGrant.user_id == uid).delete()
        obj = db.get(User, uid)
        if obj:
            db.delete(obj)
    db.commit()
    db.close()


def _encher_sessao(db, uid: int, n: int = 45) -> None:
    """n chamadas de IA nos últimos minutos — acima do teto padrão de 40/sessão."""
    agora = datetime.now(UTC)
    for i in range(n):
        db.add(AiCallLog(user_id=uid, connection_id=None, categoria="texto", origem="chat_texto",
                         modelo="m", sucesso=True, latencia_ms=1,
                         criado_em=agora - timedelta(seconds=i * 10)))
    db.commit()


def test_sem_limites_so_para_dono_e_vitalicio():
    db = SessionLocal()
    aluno = _criar(db, "sl_a")
    vit = _criar(db, "sl_v", vitalicio=True)
    dono = _criar(db, "sl_d", role="superadmin")
    try:
        assert db.get(User, aluno).sem_limites is False
        assert db.get(User, vit).sem_limites is True
        assert db.get(User, dono).sem_limites is True
    finally:
        db.close()
        _limpar(aluno, vit, dono)


def test_vitalicio_acima_do_teto_de_ritmo_nao_e_bloqueado_e_aluno_comum_continua_sendo():
    db = SessionLocal()
    set_flag(db, "limite_sessao_msgs", "40")
    vit = _criar(db, "rt_v", vitalicio=True)
    aluno = _criar(db, "rt_a")
    _encher_sessao(db, vit)
    _encher_sessao(db, aluno)
    db.close()

    quem = {"id": vit}
    app.dependency_overrides[usuario_atual] = lambda: SessionLocal().get(User, quem["id"])
    try:
        with TestClient(app) as client:
            r = client.get("/api/v1/chat/limites")
            assert r.status_code == 200, r.text
            e = r.json()
            assert e["isento"] is True and e["bloqueado"] is False, (
                "vitalício com 45 chamadas na sessão de 5h ainda foi barrado — o bug do QA"
            )

            quem["id"] = aluno
            e2 = client.get("/api/v1/chat/limites").json()
            assert e2["isento"] is False and e2["bloqueado"] is True, (
                "quem NÃO é vitalício precisa continuar com a trava de ritmo"
            )
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar(vit, aluno)
        db = SessionLocal()
        set_flag(db, "limite_sessao_msgs", limites.PADRAO_SESSAO)
        db.close()


def test_vitalicio_usa_youtube_sem_grant_e_sem_cota_aluno_comum_continua_restrito(monkeypatch):
    monkeypatch.setattr("app.api.v1.chat.buscar_videos", lambda db, termo: [])

    db = SessionLocal()
    vit = _criar(db, "yt_v", vitalicio=True)
    aluno = _criar(db, "yt_a")
    # o vitalício já gastou MUITO mais do que qualquer cota diária razoável
    for _ in range(50):
        db.add(ResourceUsageLog(user_id=vit, feature=FEATURE))
    db.commit()
    db.close()

    quem = {"id": vit}
    app.dependency_overrides[usuario_atual] = lambda: SessionLocal().get(User, quem["id"])
    try:
        with TestClient(app) as client:
            rec = client.get("/api/v1/chat/recursos").json()
            assert rec[FEATURE]["liberado"] is True and rec[FEATURE]["limite_diario"] is None

            r = client.post("/api/v1/chat/videos", json={"termo": "regra de três"})
            assert r.status_code == 200, r.text

            quem["id"] = aluno
            r2 = client.post("/api/v1/chat/videos", json={"termo": "regra de três"})
            assert r2.status_code == 403, "aluno comum sem grant do admin continua sem acesso"
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar(vit, aluno)


def test_vitalicio_nunca_estoura_cota_mesmo_com_grant_zerado():
    """A cota é limite de PESSOA; vitalício não tem, nem se o admin tiver um
    grant antigo dele com limite baixo."""
    db = SessionLocal()
    vit = _criar(db, "cq_v", vitalicio=True)
    try:
        features.conceder(db, vit, FEATURE, 1, admin_id=1)
        for _ in range(5):
            db.add(ResourceUsageLog(user_id=vit, feature=FEATURE))
        db.commit()
        u = db.get(User, vit)
        assert features.tem_acesso(db, u, FEATURE) is True
        assert features.excedeu_limite(db, u, FEATURE) is False
    finally:
        db.close()
        _limpar(vit)
