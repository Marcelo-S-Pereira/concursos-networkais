"""Cadastro de plataformas de pagamento (Mercado Pago, Stripe, Efí...).

Molde do cadastro de IA: a credencial fica cifrada no banco (AES-256-GCM). Só
superadmin. Este módulo cobre o CADASTRO; checkout/webhook/planos vêm depois.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import apenas_superadmin
from app.core.crypto import cifrar_ia, decifrar_ia, mascarar_chave
from app.core.flags import get_flag, set_flag
from app.db.models import PaymentPlatform, User
from app.db.session import get_db

router = APIRouter(prefix="/pagamentos")

PROVEDORES = {"mercadopago", "stripe", "efi", "asaas", "outro"}

# valor fixo (modelo simples do usuário): R$10 = 155 créditos por mês.
# Simulado/chat/tutor ficam atrás da porta de acesso diária ([099]) — o custo
# do dia é DERIVADO daqui (pool ÷ dias do mês corrente), não configurado à
# parte. `creditos_por_simulado`/`voz_segundos_por_credito` ficaram obsoletos
# com a porta única e saíram do schema (mostrar campo editável que não faz
# mais nada seria enganoso) — as chaves antigas no banco ficam órfãs, inofensivas.
PAG_PRECO = "pag_preco_reais"
PAG_CRED_COMPRA = "pag_creditos_compra"


class ConfigOut(BaseModel):
    preco_reais: float
    creditos_por_compra: int


class ConfigIn(BaseModel):
    preco_reais: float = Field(gt=0)
    creditos_por_compra: int = Field(gt=0)


class PlataformaIn(BaseModel):
    titulo: str = Field(min_length=1, max_length=120)
    provedor: str = "mercadopago"
    access_token: str = ""  # em branco na edição = mantém a atual
    public_key: str = ""


class PlataformaOut(BaseModel):
    id: int
    titulo: str
    provedor: str
    public_key: str
    ativa: bool
    token_mascarado: str


def _saida(p: PaymentPlatform) -> PlataformaOut:
    try:
        mascara = mascarar_chave(decifrar_ia(p.access_token_cifrado)) if p.access_token_cifrado else ""
    except Exception:  # noqa: BLE001
        mascara = "****"
    return PlataformaOut(
        id=p.id, titulo=p.titulo, provedor=p.provedor, public_key=p.public_key,
        ativa=p.ativa, token_mascarado=mascara,
    )


@router.get("/config", response_model=ConfigOut)
def obter_config(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    return ConfigOut(
        preco_reais=float(get_flag(db, PAG_PRECO, "10")),
        creditos_por_compra=int(get_flag(db, PAG_CRED_COMPRA, "155")),
    )


@router.put("/config", response_model=ConfigOut)
def salvar_config(dados: ConfigIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    set_flag(db, PAG_PRECO, str(dados.preco_reais))
    set_flag(db, PAG_CRED_COMPRA, str(dados.creditos_por_compra))
    return dados


@router.get("", response_model=list[PlataformaOut])
def listar(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    q = select(PaymentPlatform).order_by(PaymentPlatform.provedor, PaymentPlatform.id)
    return [_saida(p) for p in db.execute(q).scalars()]


@router.post("", response_model=PlataformaOut, status_code=201)
def criar(dados: PlataformaIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    if dados.provedor not in PROVEDORES:
        raise HTTPException(status_code=422, detail="Provedor inválido.")
    if not dados.access_token.strip():
        raise HTTPException(status_code=422, detail="Informe a credencial (access token).")
    p = PaymentPlatform(
        titulo=dados.titulo.strip(), provedor=dados.provedor,
        access_token_cifrado=cifrar_ia(dados.access_token.strip()),
        public_key=dados.public_key.strip(),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _saida(p)


@router.patch("/{pid}", response_model=PlataformaOut)
def editar(pid: int, dados: PlataformaIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    p = db.get(PaymentPlatform, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Plataforma não encontrada.")
    if dados.provedor not in PROVEDORES:
        raise HTTPException(status_code=422, detail="Provedor inválido.")
    p.titulo = dados.titulo.strip() or p.titulo
    p.provedor = dados.provedor
    p.public_key = dados.public_key.strip()
    if dados.access_token.strip():  # em branco = mantém a atual
        p.access_token_cifrado = cifrar_ia(dados.access_token.strip())
    db.commit()
    db.refresh(p)
    return _saida(p)


@router.delete("/{pid}", status_code=204)
def apagar(pid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    p = db.get(PaymentPlatform, pid)
    if p:
        db.delete(p)
        db.commit()


@router.get("/{pid}/revelar")
def revelar(pid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    p = db.get(PaymentPlatform, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Plataforma não encontrada.")
    return {"access_token": decifrar_ia(p.access_token_cifrado)}


@router.post("/{pid}/ativar", response_model=list[PlataformaOut])
def ativar(pid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    p = db.get(PaymentPlatform, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Plataforma não encontrada.")
    # uma ativa por provedor
    for outra in db.execute(select(PaymentPlatform).where(PaymentPlatform.provedor == p.provedor)).scalars():
        outra.ativa = outra.id == p.id
    db.commit()
    q = select(PaymentPlatform).order_by(PaymentPlatform.provedor, PaymentPlatform.id)
    return [_saida(x) for x in db.execute(q).scalars()]


@router.post("/{pid}/testar")
def testar(pid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    p = db.get(PaymentPlatform, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Plataforma não encontrada.")
    token = decifrar_ia(p.access_token_cifrado)
    if p.provedor == "mercadopago":
        try:
            r = httpx.get("https://api.mercadopago.com/users/me",
                          headers={"Authorization": f"Bearer {token}"}, timeout=15)
            if r.status_code == 200:
                d = r.json()
                conta = d.get("nickname") or d.get("email") or d.get("id")
                return {"ok": True, "mensagem": f"Conectado ao Mercado Pago: {conta}"}
            return {"ok": False, "mensagem": f"Credencial recusada ({r.status_code})."}
        except httpx.HTTPError as e:
            return {"ok": False, "mensagem": f"Falha ao contatar o Mercado Pago: {e}"}
    return {"ok": None,
            "mensagem": f"Teste automático ainda não disponível para '{p.provedor}'. A credencial está salva."}
