"""[128]: escolha do ícone de cada botão/aba — a leitura (`GET /icones`) é
pública para qualquer usuário logado, porque todo mundo precisa ver o
ícone renderizado; escrever (biblioteca/upload/remover) é só admin."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import apenas_superadmin, usuario_atual
from app.db.models import User
from app.db.session import get_db
from app.modules.icones import icones

router = APIRouter(prefix="/icones")


@router.get("")
def listar(_: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    return icones.estado(db)


@router.get("/arquivo/{slot}")
def arquivo(slot: str, _: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    estado_atual = icones.estado(db).get(slot)
    if not estado_atual or estado_atual["tipo"] != "upload":
        raise HTTPException(status_code=404, detail="Sem ícone enviado para este slot.")
    caminho = icones.caminho_upload(estado_atual["valor"])
    if not caminho.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return FileResponse(caminho)


@router.get("/admin/catalogo")
def catalogo(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    return icones.catalogo_com_estado(db)


class BibliotecaIn(BaseModel):
    nome_icone: str


@router.put("/admin/{slot}")
def definir_biblioteca(
    slot: str, dados: BibliotecaIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db),
):
    try:
        icones.definir_biblioteca(db, slot, dados.nome_icone)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return icones.catalogo_com_estado(db)


@router.post("/admin/{slot}/upload")
async def enviar_upload(
    slot: str, arquivo: UploadFile, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db),
):
    dados = await arquivo.read()
    try:
        icones.definir_upload(db, slot, arquivo.filename or "", dados)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return icones.catalogo_com_estado(db)


@router.delete("/admin/{slot}")
def apagar(slot: str, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    icones.remover(db, slot)
    return icones.catalogo_com_estado(db)
