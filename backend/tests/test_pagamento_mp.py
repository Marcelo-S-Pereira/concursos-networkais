"""[112]: checkout de créditos via Mercado Pago. Sem token real de produção —
httpx mockado, mesmo padrão honesto de test_youtube.py. A garantia central
testada aqui: o webhook NUNCA confia no status que vem na notificação, só no
que a própria API da MP devolve pra aquele payment_id; e é idempotente."""

import unittest.mock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import usuario_atual
from app.core.crypto import cifrar_ia
from app.db.models import CreditTransaction, PaymentPlatform, User
from app.db.session import SessionLocal
from app.main import app
from app.modules.creditos.carteira import creditar, saldo


def _usuario(sufixo: str) -> User:
    db = SessionLocal()
    u = User(nome="Teste MP", email=f"t_mp_{sufixo}@teste_test.local", cpf_cifrado="x",
              cpf_indice=f"idx_mp_{sufixo}", telefone="x", role="aluno")
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


def _limpar(uid: int, plat_id: int | None = None) -> None:
    db = SessionLocal()
    db.query(CreditTransaction).filter(CreditTransaction.user_id == uid).delete()
    db.query(User).filter(User.id == uid).delete()
    if plat_id:
        db.query(PaymentPlatform).filter(PaymentPlatform.id == plat_id).delete()
    db.commit()
    db.close()


def test_comprar_sem_plataforma_ativa_da_400():
    u = _usuario("sem_plataforma")
    app.dependency_overrides[usuario_atual] = lambda: u
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/creditos/comprar")
        assert r.status_code == 400
        assert "plataforma" in r.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar(u.id)


@pytest.fixture
def plataforma_mp():
    db = SessionLocal()
    p = PaymentPlatform(titulo="MP teste", provedor="mercadopago",
                        access_token_cifrado=cifrar_ia("token-fake"), ativa=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    db.close()
    yield p
    db = SessionLocal()
    db.query(PaymentPlatform).filter(PaymentPlatform.id == p.id).delete()
    db.commit()
    db.close()


def test_comprar_cria_preferencia_e_devolve_init_point(plataforma_mp):
    u = _usuario("comprar_ok")

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url.endswith("/checkout/preferences")
        assert json["external_reference"] == f"user:{u.id}:creditos:155"
        return httpx.Response(201, json={"id": "pref-1", "init_point": "https://mp.example/pagar/pref-1"},
                              request=httpx.Request("POST", url))

    app.dependency_overrides[usuario_atual] = lambda: u
    try:
        with unittest.mock.patch.object(httpx, "post", fake_post), TestClient(app) as client:
            r = client.post("/api/v1/creditos/comprar")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["init_point"] == "https://mp.example/pagar/pref-1"
        assert corpo["creditos"] == 155
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar(u.id)


def test_webhook_aprovado_credita_uma_vez_e_ignora_reenvio(plataforma_mp):
    u = _usuario("webhook_ok")

    def fake_get(url, headers=None, timeout=None):
        assert url.endswith("/v1/payments/999")
        return httpx.Response(200, json={"status": "approved",
                                          "external_reference": f"user:{u.id}:creditos:155"},
                              request=httpx.Request("GET", url))

    with unittest.mock.patch.object(httpx, "get", fake_get), TestClient(app) as client:
        r1 = client.post("/api/v1/creditos/webhook?type=payment&data.id=999")
        assert r1.status_code == 200
        r2 = client.post("/api/v1/creditos/webhook?type=payment&data.id=999")  # MP reenvia
        assert r2.status_code == 200

    db = SessionLocal()
    assert saldo(db, u.id) == 155  # creditou só uma vez, não duas
    db.close()
    _limpar(u.id)


def test_webhook_status_nao_aprovado_nao_credita(plataforma_mp):
    u = _usuario("webhook_pendente")

    def fake_get(url, headers=None, timeout=None):
        return httpx.Response(200, json={"status": "pending",
                                          "external_reference": f"user:{u.id}:creditos:155"},
                              request=httpx.Request("GET", url))

    with unittest.mock.patch.object(httpx, "get", fake_get), TestClient(app) as client:
        r = client.post("/api/v1/creditos/webhook?type=payment&data.id=1000")
        assert r.status_code == 200

    db = SessionLocal()
    assert saldo(db, u.id) == 0  # nunca confiou em nada além do status "approved"
    db.close()
    _limpar(u.id)


def test_webhook_ignora_notificacao_que_nao_e_pagamento():
    with TestClient(app) as client:
        r = client.post("/api/v1/creditos/webhook?topic=merchant_order&id=1")
    assert r.status_code == 200  # devolve 200 sem tentar processar nada


def test_extrato_ja_com_100_transacoes_nao_permite_credito_duplicado_do_webhook(plataforma_mp):
    """Idempotência real: mesmo depois de muitas transações (mais do que os 50
    do extrato resumido), o webhook não pode creditar duas vezes o mesmo
    payment_id — a checagem consulta a tabela inteira, não o resumo truncado."""
    u = _usuario("muitas_tx")
    db = SessionLocal()
    for _ in range(60):
        creditar(db, u.id, 1, "bonus", "ruido")
    db.close()

    def fake_get(url, headers=None, timeout=None):
        return httpx.Response(200, json={"status": "approved",
                                          "external_reference": f"user:{u.id}:creditos:155"},
                              request=httpx.Request("GET", url))

    with unittest.mock.patch.object(httpx, "get", fake_get), TestClient(app) as client:
        client.post("/api/v1/creditos/webhook?type=payment&data.id=2000")
        client.post("/api/v1/creditos/webhook?type=payment&data.id=2000")

    db = SessionLocal()
    assert saldo(db, u.id) == 60 + 155  # creditou só uma vez apesar das 60 transações antigas
    db.close()
    _limpar(u.id)
