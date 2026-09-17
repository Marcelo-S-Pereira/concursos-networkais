"""[153]: BETA 1 — os N primeiros cadastros (`role="aluno"`) ganham o
crédito do mês automaticamente; a partir daí, ninguém mais ganha sem ação
manual do admin. E o widget de feedback (POST /feedback)."""

from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import usuario_atual
from app.core.flags import BETA_VAGAS_TOTAL, BETA_VAGAS_TOTAL_PADRAO, set_flag
from app.db.models import CreditTransaction, Feedback, User
from app.db.session import SessionLocal, get_db
from app.main import app


def test_beta_credita_automatico_so_dentro_da_janela_de_vagas():
    db = SessionLocal()
    # [153]: `cadastrar()` só marca "aluno" quem NÃO é o 1º usuário do banco
    # inteiro (o 1º vira superadmin, sem bônus) — garante que já existe
    # alguém no banco de teste, senão o próprio "Beta A" viraria admin.
    ja_existe_alguem = db.execute(select(User.id).limit(1)).scalar_one_or_none() is not None
    ancora = None
    if not ja_existe_alguem:
        ancora = User(nome="Âncora", email="ancora_beta_test_153@teste_test.local", cpf_cifrado="x",
                      cpf_indice="idx_ancora_beta_test", telefone="x", role="superadmin")
        db.add(ancora)
        db.commit()
        db.refresh(ancora)

    alunos_antes = db.execute(select(User.id).where(User.role == "aluno")).scalars().all()
    # só 1 vaga a mais que o que já existe — o próximo cadastro pega, o depois não
    set_flag(db, BETA_VAGAS_TOTAL, str(len(alunos_antes) + 1))
    db.close()

    with TestClient(app) as client:
        rbeta = client.get("/api/v1/auth/beta")
        assert rbeta.status_code == 200
        assert rbeta.json()["vagas_restantes"] == 1

        rA = client.post("/api/v1/auth/cadastro", json={
            "nome": "Beta A", "email": "beta_a_test_153@example.com",
            "cpf": "[CPF_TESTE_REMOVIDO]", "telefone": "[TELEFONE_TESTE_REMOVIDO]",
        })
        assert rA.status_code == 201

        rB = client.post("/api/v1/auth/cadastro", json={
            "nome": "Beta B", "email": "beta_b_test_153@example.com",
            "cpf": "[CPF_TESTE_REMOVIDO]", "telefone": "[TELEFONE_TESTE_REMOVIDO]",
        })
        assert rB.status_code == 201

        rbeta2 = client.get("/api/v1/auth/beta")
        assert rbeta2.json()["vagas_restantes"] == 0

    db = SessionLocal()
    try:
        ua = db.execute(select(User).where(User.email == "beta_a_test_153@example.com")).scalar_one()
        ub = db.execute(select(User).where(User.email == "beta_b_test_153@example.com")).scalar_one()

        ta = db.execute(select(CreditTransaction).where(CreditTransaction.user_id == ua.id)).scalars().all()
        tb = db.execute(select(CreditTransaction).where(CreditTransaction.user_id == ub.id)).scalars().all()
        assert len(ta) == 1 and ta[0].delta == 155 and ta[0].tipo == "bonus"
        assert len(tb) == 0  # a vaga já tinha acabado com o cadastro A
    finally:
        db.execute(CreditTransaction.__table__.delete().where(CreditTransaction.user_id.in_([ua.id, ub.id])))
        db.delete(ua)
        db.delete(ub)
        if ancora is not None:
            db.delete(db.get(User, ancora.id))
        set_flag(db, BETA_VAGAS_TOTAL, str(BETA_VAGAS_TOTAL_PADRAO))
        db.commit()
        db.close()


def test_feedback_exige_estrelas_ou_texto_e_persiste():
    db = SessionLocal()
    u = User(nome="T", email="t_feedback@teste_test.local", cpf_cifrado="x",
             cpf_indice="idx_feedback_test", telefone="x", role="aluno")
    db.add(u)
    db.commit()
    db.refresh(u)

    def _override(uid: int):
        def dep(db: Session = Depends(get_db)) -> User:
            return db.get(User, uid)
        return dep

    app.dependency_overrides[usuario_atual] = _override(u.id)
    try:
        with TestClient(app) as client:
            vazio = client.post("/api/v1/feedback", json={"ferramenta": "chat"})
            assert vazio.status_code == 422

            invalida = client.post("/api/v1/feedback", json={"ferramenta": "x", "estrelas": 5})
            assert invalida.status_code == 422

            ok = client.post("/api/v1/feedback", json={"ferramenta": "tutor_ia", "estrelas": 4, "texto": "muito bom"})
            assert ok.status_code == 201
    finally:
        app.dependency_overrides.clear()
        db.query(Feedback).filter(Feedback.user_id == u.id).delete()
        db.delete(u)
        db.commit()
        db.close()
