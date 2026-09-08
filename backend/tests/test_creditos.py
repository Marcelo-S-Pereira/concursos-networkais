"""Carteira de créditos: creditar e resumir (saldo/ganho/gasto/extrato)."""

from app.db.models import CreditTransaction, User
from app.db.session import SessionLocal
from app.modules.creditos.carteira import creditar, resumo, saldo


def test_creditar_e_resumir():
    db = SessionLocal()
    u = User(nome="T", email="t_cred@teste_test.local", cpf_cifrado="x",
             cpf_indice="idx_cred_test", telefone="x", role="aluno")
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    db.close()

    try:
        db = SessionLocal()
        creditar(db, uid, 100, "compra", "compra de 100 créditos")
        creditar(db, uid, 50, "bonus", "cortesia")
        creditar(db, uid, -100, "gasto_simulado", "simulado Dutos")
        r = resumo(db, uid)
        assert r["total_ganho"] == 150
        assert r["total_gasto"] == 100
        assert r["saldo"] == 50
        assert saldo(db, uid) == 50
        assert len(r["extrato"]) == 3
        # extrato em ordem decrescente: o gasto (último lançado) vem primeiro
        assert r["extrato"][0]["delta"] == -100
        db.close()
    finally:
        db = SessionLocal()
        db.query(CreditTransaction).filter(CreditTransaction.user_id == uid).delete()
        obj = db.get(User, uid)
        if obj:
            db.delete(obj)
        db.commit()
        db.close()
