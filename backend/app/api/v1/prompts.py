"""[125]: aba Prompts (admin) — a base de dados é a ÚNICA fonte de verdade do
texto enviado à IA. Listar mostra nome/onde é usado/como funciona/texto de
cada prompt; editar muda só `texto` (os metadados descritivos não são
editáveis pela tela — são o que documenta o que o campo `texto` faz)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import apenas_superadmin
from app.db.models import Prompt, User
from app.db.session import get_db

router = APIRouter(prefix="/prompts")


class PromptOut(BaseModel):
    chave: str
    nome: str
    onde_usado: str
    como_funciona: str
    texto: str


@router.get("", response_model=list[PromptOut])
def listar(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    linhas = db.execute(select(Prompt).order_by(Prompt.nome)).scalars().all()
    return [PromptOut(chave=p.chave, nome=p.nome, onde_usado=p.onde_usado,
                       como_funciona=p.como_funciona, texto=p.texto) for p in linhas]


class EditarPromptIn(BaseModel):
    texto: str


@router.put("/{chave}", response_model=PromptOut)
def editar(chave: str, dados: EditarPromptIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    prompt = db.get(Prompt, chave)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt não encontrado.")
    texto = dados.texto.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="O texto do prompt não pode ficar vazio.")
    prompt.texto = texto
    db.commit()
    return PromptOut(chave=prompt.chave, nome=prompt.nome, onde_usado=prompt.onde_usado,
                      como_funciona=prompt.como_funciona, texto=prompt.texto)
