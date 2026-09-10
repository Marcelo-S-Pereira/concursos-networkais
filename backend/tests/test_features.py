"""Liberação de recursos restritos por usuário, com cota diária.

O que importa testar de verdade é a SEMÂNTICA da cota: sem grant = sem acesso;
com grant, conta o uso real e bloqueia ao atingir o limite; superadmin sempre
passa, mas o uso dele também soma no total do pool (é cota real do provedor)."""

from app.db.models import FeatureGrant, ResourceUsageLog, User
from app.db.session import SessionLocal
from app.modules.features import features

FEATURE = "youtube_videos"


def _criar_usuario(db, sufixo: str, role: str = "aluno") -> int:
    u = User(nome="F", email=f"t_feat{sufixo}@teste_test.local", cpf_cifrado="x",
             cpf_indice=f"idx_feat_{sufixo}", telefone="x", role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u.id


def _limpar(*uids: int) -> None:
    db = SessionLocal()
    for uid in uids:
        db.query(ResourceUsageLog).filter(ResourceUsageLog.user_id == uid).delete()
        db.query(FeatureGrant).filter(FeatureGrant.user_id == uid).delete()
        obj = db.get(User, uid)
        if obj:
            db.delete(obj)
    db.commit()
    db.close()


def test_sem_grant_sem_acesso_com_grant_libera():
    db = SessionLocal()
    uid = _criar_usuario(db, "a")
    try:
        u = db.get(User, uid)
        assert features.tem_acesso(db, u, FEATURE) is False
        assert features.excedeu_limite(db, u, FEATURE) is True  # sem grant = bloqueado

        features.conceder(db, uid, FEATURE, 3, admin_id=1)
        u = db.get(User, uid)
        assert features.tem_acesso(db, u, FEATURE) is True
        assert features.limite_diario(db, uid, FEATURE) == 3
        assert features.usado_hoje(db, uid, FEATURE) == 0
        assert features.excedeu_limite(db, u, FEATURE) is False
        db.close()
    finally:
        _limpar(uid)


def test_cota_bloqueia_ao_atingir_o_limite():
    db = SessionLocal()
    uid = _criar_usuario(db, "b")
    try:
        features.conceder(db, uid, FEATURE, 2, admin_id=1)
        u = db.get(User, uid)
        features.registrar_uso(db, uid, FEATURE)
        assert features.excedeu_limite(db, u, FEATURE) is False  # 1/2
        features.registrar_uso(db, uid, FEATURE)
        assert features.usado_hoje(db, uid, FEATURE) == 2
        assert features.excedeu_limite(db, u, FEATURE) is True  # 2/2, estourou
        db.close()
    finally:
        _limpar(uid)


def test_revogar_tira_o_acesso():
    db = SessionLocal()
    uid = _criar_usuario(db, "c")
    try:
        features.conceder(db, uid, FEATURE, 5, admin_id=1)
        u = db.get(User, uid)
        assert features.tem_acesso(db, u, FEATURE) is True
        features.revogar(db, uid, FEATURE)
        u = db.get(User, uid)
        assert features.tem_acesso(db, u, FEATURE) is False
        db.close()
    finally:
        _limpar(uid)


def test_superadmin_nunca_bloqueado_mas_uso_soma_no_pool():
    db = SessionLocal()
    uid = _criar_usuario(db, "d", role="superadmin")
    try:
        u = db.get(User, uid)
        assert features.tem_acesso(db, u, FEATURE) is True  # sem grant nenhum
        assert features.excedeu_limite(db, u, FEATURE) is False

        antes = features.uso_total_hoje(db, FEATURE)
        features.registrar_uso(db, uid, FEATURE)
        assert features.uso_total_hoje(db, FEATURE) == antes + 1
        assert features.excedeu_limite(db, u, FEATURE) is False  # continua liberado
        db.close()
    finally:
        _limpar(uid)


def test_pool_soma_o_uso_de_varios_usuarios():
    db = SessionLocal()
    uid1 = _criar_usuario(db, "e1")
    uid2 = _criar_usuario(db, "e2")
    try:
        antes = features.uso_total_hoje(db, FEATURE)
        features.registrar_uso(db, uid1, FEATURE)
        features.registrar_uso(db, uid2, FEATURE)
        features.registrar_uso(db, uid2, FEATURE)
        assert features.uso_total_hoje(db, FEATURE) == antes + 3
        db.close()
    finally:
        _limpar(uid1, uid2)
