"""Checkout Pro do Mercado Pago ([075]/[112]): cria a preferência de compra
de créditos e consulta um pagamento pelo id.

A AUTORIDADE do status de um pagamento é sempre a API da MP, consultada aqui
com o token da conta — nunca o corpo de uma notificação de webhook, que
qualquer um pode forjar. `consultar_pagamento` é o único lugar que decide se
um pagamento foi de fato aprovado.
"""

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decifrar_ia
from app.db.models import PaymentPlatform

TIMEOUT_S = 20.0


class MercadoPagoError(Exception):
    pass


def _token_ativo(db: Session) -> str | None:
    p = db.execute(
        select(PaymentPlatform).where(PaymentPlatform.provedor == "mercadopago", PaymentPlatform.ativa.is_(True))
    ).scalars().first()
    if not p or not p.access_token_cifrado:
        return None
    return decifrar_ia(p.access_token_cifrado)


def criar_preferencia(db: Session, *, user_id: int, creditos: int, preco_reais: float, base_url: str) -> dict:
    """Cria a preferência de Checkout Pro. Devolve {"id": ..., "init_point": ...}."""
    token = _token_ativo(db)
    if not token:
        raise MercadoPagoError("Nenhuma plataforma Mercado Pago ativa. Cadastre e ative em Pagamentos.")

    corpo = {
        "items": [{
            "title": f"{creditos} créditos — Conlibrarie",
            "quantity": 1,
            "unit_price": round(preco_reais, 2),
            "currency_id": "BRL",
        }],
        "external_reference": f"user:{user_id}:creditos:{creditos}",
        "notification_url": f"{base_url}/api/v1/creditos/webhook",
        "back_urls": {
            "success": base_url, "failure": base_url, "pending": base_url,
        },
        "auto_return": "approved",
    }
    try:
        r = httpx.post(
            "https://api.mercadopago.com/checkout/preferences",
            headers={"Authorization": f"Bearer {token}"}, json=corpo, timeout=TIMEOUT_S,
        )
    except httpx.HTTPError as e:
        raise MercadoPagoError(f"Falha ao contatar o Mercado Pago: {e}") from e
    if r.status_code >= 400:
        raise MercadoPagoError(f"Mercado Pago recusou a preferência ({r.status_code}): {r.text[:300]}")
    dados = r.json()
    return {"id": dados.get("id"), "init_point": dados.get("init_point")}


def consultar_pagamento(db: Session, payment_id: str) -> dict | None:
    """GET /v1/payments/{id}. Devolve {"status": ..., "external_reference": ...}
    ou None se o token não estiver configurado ou o pagamento não existir."""
    token = _token_ativo(db)
    if not token:
        return None
    try:
        r = httpx.get(
            f"https://api.mercadopago.com/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT_S,
        )
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    dados = r.json()
    return {"status": dados.get("status"), "external_reference": dados.get("external_reference") or ""}
