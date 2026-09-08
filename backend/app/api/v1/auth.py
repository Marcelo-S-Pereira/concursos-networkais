import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import usuario_atual
from app.core.crypto import cifrar, indice_deterministico
from app.core.validadores import cpf_valido, mascarar_cpf, normalizar_digitos, telefone_valido
from app.db.models import LoginCode, User
from app.db.session import get_db
from app.integrations.email.enviar import MINUTOS_VALIDADE, enviar_codigo

router = APIRouter(prefix="/auth")

MAX_TENTATIVAS = 5


def _hash_codigo(codigo: str) -> str:
    """Guardamos o hash, não o código. Se o banco vazar, os códigos ainda
    válidos não servem para entrar em conta nenhuma."""
    return hashlib.sha256(codigo.encode()).hexdigest()


class CadastroIn(BaseModel):
    nome: str = Field(min_length=3, max_length=160)
    email: EmailStr
    cpf: str
    telefone: str


class EmailIn(BaseModel):
    email: EmailStr


class VerificarIn(BaseModel):
    email: EmailStr
    codigo: str = Field(min_length=6, max_length=6)


class UsuarioOut(BaseModel):
    id: int
    nome: str
    email: str
    cpf: str  # sempre mascarado
    telefone: str
    role: str


def _para_saida(u: User) -> UsuarioOut:
    from app.core.crypto import decifrar

    return UsuarioOut(
        id=u.id,
        nome=u.nome,
        email=u.email,
        cpf=mascarar_cpf(decifrar(u.cpf_cifrado)),
        telefone=u.telefone,
        role=u.role,
    )


@router.post("/cadastro", status_code=status.HTTP_201_CREATED)
def cadastrar(dados: CadastroIn, db: Session = Depends(get_db)) -> dict:
    from app.core.flags import cadastros_bloqueados

    # protege a ambiente de execucao: quando o admin bloqueia (ou o monitor auto-bloqueia em carga
    # crítica), novos cadastros são recusados. O dono já existe, não é afetado.
    ja_tem_usuario = db.execute(select(User.id).limit(1)).scalar_one_or_none() is not None
    if ja_tem_usuario and cadastros_bloqueados(db):
        raise HTTPException(status_code=403, detail="Cadastros temporariamente fechados. Tente mais tarde.")

    cpf = normalizar_digitos(dados.cpf)
    telefone = normalizar_digitos(dados.telefone)

    if not cpf_valido(cpf):
        raise HTTPException(status_code=422, detail="CPF inválido.")
    if not telefone_valido(telefone):
        raise HTTPException(status_code=422, detail="Telefone inválido. Use DDD + número.")

    email = dados.email.lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado. Faça login.")

    indice = indice_deterministico(cpf, "cpf")
    if db.execute(select(User).where(User.cpf_indice == indice)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Este CPF já está cadastrado.")

    # O primeiro cadastro do sistema é o dono.
    primeiro = db.execute(select(User.id).limit(1)).scalar_one_or_none() is None

    db.add(
        User(
            nome=dados.nome.strip(),
            email=email,
            cpf_cifrado=cifrar(cpf),
            cpf_indice=indice,
            telefone=telefone,
            role="superadmin" if primeiro else "aluno",
        )
    )
    db.commit()
    return {"mensagem": "Cadastro realizado. Agora entre com o código enviado ao seu e-mail."}


@router.post("/login/solicitar")
def solicitar_codigo(dados: EmailIn, db: Session = Depends(get_db)) -> dict:
    email = dados.email.lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="E-mail não cadastrado. Faça o cadastro primeiro.")

    # Invalida códigos anteriores: pedir um novo derruba o antigo.
    agora = datetime.now(UTC)
    for antigo in db.execute(
        select(LoginCode).where(LoginCode.user_id == user.id, LoginCode.usado_em.is_(None))
    ).scalars():
        antigo.usado_em = agora

    codigo = f"{secrets.randbelow(1_000_000):06d}"
    db.add(
        LoginCode(
            user_id=user.id,
            codigo_hash=_hash_codigo(codigo),
            expira_em=agora + timedelta(minutes=MINUTOS_VALIDADE),
        )
    )
    db.commit()

    enviado = enviar_codigo(user.email, user.nome.split()[0], codigo)
    # A resposta é a mesma tendo o e-mail saído ou não - detalhe de SMTP não é
    # assunto de quem está entrando. A falha fica no log do serviço.
    return {"mensagem": f"Código enviado para {user.email}. Vale por {MINUTOS_VALIDADE} minutos.", "enviado": enviado}


@router.post("/login/verificar", response_model=UsuarioOut)
def verificar_codigo(dados: VerificarIn, request: Request, db: Session = Depends(get_db)):
    email = dados.email.lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Código inválido ou expirado.")

    agora = datetime.now(UTC)
    codigo = db.execute(
        select(LoginCode)
        .where(LoginCode.user_id == user.id, LoginCode.usado_em.is_(None))
        .order_by(LoginCode.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if not codigo or codigo.expira_em <= agora:
        raise HTTPException(status_code=401, detail="Código inválido ou expirado.")

    if codigo.tentativas >= MAX_TENTATIVAS:
        codigo.usado_em = agora
        db.commit()
        raise HTTPException(status_code=429, detail="Tentativas demais. Peça um código novo.")

    if not secrets.compare_digest(codigo.codigo_hash, _hash_codigo(dados.codigo)):
        codigo.tentativas += 1
        db.commit()
        raise HTTPException(status_code=401, detail="Código inválido ou expirado.")

    codigo.usado_em = agora  # uso único
    db.commit()

    request.session.clear()  # sessão nova a cada login, contra fixação
    request.session["user_id"] = user.id
    return _para_saida(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> None:
    request.session.clear()


@router.get("/me", response_model=UsuarioOut)
def me(user: User = Depends(usuario_atual)):
    return _para_saida(user)
