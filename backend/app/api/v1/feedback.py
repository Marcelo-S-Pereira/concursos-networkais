"""[153]: feedback do usuário sobre uma ferramenta (Chat de estudo/Tutor
IA/Simulado) — estrelas e/ou texto. Fica salvo e dispara um e-mail pro
dono; o e-mail é best-effort (o feedback conta mesmo se o envio falhar)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import usuario_atual
from app.db.models import Feedback, User
from app.db.session import get_db
from app.integrations.email.enviar import enviar_email

router = APIRouter(prefix="/feedback")

FERRAMENTAS = ("chat", "tutor_ia", "simulado")
EMAIL_DESTINO = "[EMAIL_REMOVIDO]"

NOME_FERRAMENTA = {"chat": "Chat de estudo", "tutor_ia": "Tutor IA", "simulado": "Simulado/Caderno de questões"}


class FeedbackIn(BaseModel):
    ferramenta: str
    estrelas: int | None = None
    texto: str | None = None


@router.post("", status_code=201)
def enviar(dados: FeedbackIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    if dados.ferramenta not in FERRAMENTAS:
        raise HTTPException(status_code=422, detail=f"ferramenta inválida — use uma de {FERRAMENTAS}")
    if dados.estrelas is not None and not (1 <= dados.estrelas <= 5):
        raise HTTPException(status_code=422, detail="estrelas deve ser de 1 a 5.")
    if dados.estrelas is None and not (dados.texto or "").strip():
        raise HTTPException(status_code=422, detail="Mande estrelas, texto, ou os dois.")

    f = Feedback(
        user_id=user.id, ferramenta=dados.ferramenta,
        estrelas=dados.estrelas, texto=(dados.texto or "").strip() or None,
    )
    db.add(f)
    db.commit()

    nome_ferr = NOME_FERRAMENTA.get(dados.ferramenta, dados.ferramenta)
    estrelas_txt = f"{dados.estrelas}/5" if dados.estrelas else "(sem nota)"
    corpo = (
        f"Feedback novo — {nome_ferr}\n\n"
        f"De: {user.nome} <{user.email}>\n"
        f"Estrelas: {estrelas_txt}\n"
        f"Texto: {(dados.texto or '').strip() or '(sem texto)'}\n"
    )
    enviar_email(EMAIL_DESTINO, f"Feedback — {nome_ferr}", corpo)
    return {"ok": True}
