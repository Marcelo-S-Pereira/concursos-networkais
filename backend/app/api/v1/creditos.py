"""Carteira de créditos do próprio usuário (saldo, ganho, gasto, extrato) +
checkout de compra via Mercado Pago ([075]/[112])."""

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import usuario_atual
from app.api.v1.pagamentos import PAG_CRED_COMPRA, PAG_PRECO
from app.core.flags import get_flag
from app.db.models import CreditTransaction, User
from app.db.session import get_db
from app.modules.creditos import acesso_diario
from app.modules.creditos.carteira import creditar, resumo
from app.modules.pagamento.mercadopago import MercadoPagoError, consultar_pagamento, criar_preferencia

router = APIRouter(prefix="/creditos")

BASE_URL = "https://concursos.networkais.com"
PADRAO_REFERENCIA = re.compile(r"^user:(\d+):creditos:(\d+)$")


@router.get("")
def meus_creditos(user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    r = resumo(db, user.id)
    # acesso livre (não consome crédito): o dono OU quem tem vitalício. Decidido no
    # servidor a partir do banco — o cliente não influencia isto.
    r["acesso_livre"] = user.sem_limites
    r["vitalicio"] = user.vitalicio
    return r


@router.get("/porta")
def minha_porta(user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Estado da porta de acesso diária ([099]/[100]/[101]): pra montar a
    barra de hoje (contagem regressiva) e a da semana (gasto da semana ÷ alvo
    semanal = 7 × custo do dia)."""
    return {"hoje": acesso_diario.estado_hoje(db, user), "semana": acesso_diario.resumo_semana(db, user)}


@router.post("/comprar")
def comprar(user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """[112]: cria a preferência de Checkout Pro pro valor fixo configurado
    em Pagamentos ([069]). 400 claro se não houver plataforma MP ativa —
    nunca finge que funciona sem token."""
    preco = float(get_flag(db, PAG_PRECO, "10"))
    creditos = int(get_flag(db, PAG_CRED_COMPRA, "155"))
    try:
        pref = criar_preferencia(db, user_id=user.id, creditos=creditos, preco_reais=preco, base_url=BASE_URL)
    except MercadoPagoError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"init_point": pref["init_point"], "creditos": creditos, "preco_reais": preco}


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """[112]: chamado pela Mercado Pago, sem sessão — é o servidor deles, não
    um usuário logado. NUNCA confia no status que vem no corpo/query da
    notificação (qualquer um poderia forjar isso); sempre consulta o
    pagamento de volta na API da MP com o nosso token, que é a única
    autoridade. Idempotente por "mp:{payment_id}" na descrição — uma segunda
    notificação do mesmo pagamento não credita de novo. Sempre devolve 200
    (melhor esforço — a MP reenvia em loop se receber erro; quem quer saber
    se creditou confere o próprio saldo)."""
    qp = request.query_params
    tipo = qp.get("type") or qp.get("topic")
    payment_id = qp.get("data.id") or qp.get("id")
    if not payment_id:
        try:
            corpo = await request.json()
        except Exception:  # noqa: BLE001
            corpo = {}
        tipo = tipo or corpo.get("type") or corpo.get("action", "").split(".")[0]
        payment_id = payment_id or (corpo.get("data") or {}).get("id")

    if tipo != "payment" or not payment_id:
        return {"ok": True}  # notificação de outro tipo (ex: merchant_order) — ignorada

    pagamento = consultar_pagamento(db, str(payment_id))
    if not pagamento or pagamento["status"] != "approved":
        return {"ok": True}

    m = PADRAO_REFERENCIA.match(pagamento["external_reference"])
    if not m:
        return {"ok": True}
    user_id, creditos = int(m.group(1)), int(m.group(2))

    marca = f"mp:{payment_id}"
    ja_creditado = db.execute(
        select(CreditTransaction.id).where(
            CreditTransaction.user_id == user_id, CreditTransaction.descricao.contains(marca)
        )
    ).first()
    if not ja_creditado:
        creditar(db, user_id, creditos, "compra", f"Compra via Mercado Pago ({marca})")
    return {"ok": True}
