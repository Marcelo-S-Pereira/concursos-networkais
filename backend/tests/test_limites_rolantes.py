"""Limites rolantes de uso de IA (estilo plataforma de estudo).

O que precisa estar certo aqui é a SEMÂNTICA da sessão: a janela de 5h é ancorada
na primeira mensagem, não deslizante. Uma chamada 5h depois da âncora abre sessão
nova; e uma sessão cuja âncora já passou de 5h está morta (contagem zera).
"""

from datetime import UTC, datetime, timedelta

from app.core.flags import set_flag
from app.db.models import AiCallLog, SystemSetting, User
from app.db.session import SessionLocal
from app.modules.ai_registry import limites


def _log(uid: int, quando: datetime) -> AiCallLog:
    return AiCallLog(user_id=uid, connection_id=None, categoria="texto", origem="chat_texto",
                     modelo="m", sucesso=True, latencia_ms=1, criado_em=quando)


def _criar_usuario(db, sufixo: str) -> int:
    u = User(nome="L", email=f"t_lim{sufixo}@teste_test.local", cpf_cifrado="x",
             cpf_indice=f"idx_lim_{sufixo}", telefone="x", role="aluno")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u.id


def _limpar(uid: int) -> None:
    db = SessionLocal()
    db.query(AiCallLog).filter(AiCallLog.user_id == uid).delete()
    obj = db.get(User, uid)
    if obj:
        db.delete(obj)
    for chave in ("limite_sessao_msgs", "limite_semana_msgs"):
        row = db.get(SystemSetting, chave)
        if row:
            db.delete(row)
    db.commit()
    db.close()


def test_sessao_ancorada_e_semana_rolante():
    db = SessionLocal()
    uid = _criar_usuario(db, "a")
    agora = datetime.now(UTC)
    # 3 chamadas na sessão viva (âncora 2h atrás) + 2 de 3 dias atrás, que ficam
    # na semana mas pertencem a uma sessão já expirada.
    for delta in (timedelta(days=3, minutes=10), timedelta(days=3),
                  timedelta(hours=2), timedelta(hours=1), timedelta(minutes=5)):
        db.add(_log(uid, agora - delta))
    db.commit()
    db.close()

    try:
        db = SessionLocal()
        e = limites.estado(db, uid)
        assert e["sessao"]["usadas"] == 3, "só as 3 da sessão viva contam na sessão"
        assert e["semana"]["usadas"] == 5, "as 5 estão dentro dos 7 dias"
        assert e["sessao"]["reinicia_em"] is not None
        assert e["bloqueado"] is False

        # teto de sessão atingido → bloqueio explicando a sessão
        set_flag(db, "limite_sessao_msgs", "3")
        set_flag(db, "limite_semana_msgs", "0")
        motivo = limites.bloqueio(db, uid)
        assert motivo and "sessão" in motivo and "3/3" in motivo
        assert limites.bloqueio(db, uid, isento=True) is None, "o dono não é limitado"

        # teto de sessão folgado, teto semanal apertado → bloqueio semanal
        set_flag(db, "limite_sessao_msgs", "50")
        set_flag(db, "limite_semana_msgs", "5")
        motivo = limites.bloqueio(db, uid)
        assert motivo and "semanal" in motivo and "5/5" in motivo

        # 0 = sem limite
        set_flag(db, "limite_sessao_msgs", "0")
        set_flag(db, "limite_semana_msgs", "0")
        assert limites.bloqueio(db, uid) is None
        db.close()
    finally:
        _limpar(uid)


def test_sessao_expirada_zera_a_contagem():
    db = SessionLocal()
    uid = _criar_usuario(db, "b")
    agora = datetime.now(UTC)
    # tudo com mais de 5h: a sessão morreu, mas a semana ainda conta
    for delta in (timedelta(hours=9), timedelta(hours=8)):
        db.add(_log(uid, agora - delta))
    db.commit()
    db.close()

    try:
        db = SessionLocal()
        e = limites.estado(db, uid)
        assert e["sessao"]["usadas"] == 0, "sessão expirada não conta"
        assert e["sessao"]["reinicia_em"] is None
        assert e["semana"]["usadas"] == 2
        db.close()
    finally:
        _limpar(uid)
