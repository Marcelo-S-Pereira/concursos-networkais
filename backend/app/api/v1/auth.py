import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
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

# [118]: login por senha — mesmo espírito de lockout do LoginCode.tentativas,
# mas por conta (não por código), já que a senha é reusável indefinidamente.
MAX_TENTATIVAS_SENHA = 5
BLOQUEIO_SENHA_MINUTOS = 15


def _hash_codigo(codigo: str) -> str:
    """Guardamos o hash, não o código. Se o banco vazar, os códigos ainda
    válidos não servem para entrar em conta nenhuma."""
    return hashlib.sha256(codigo.encode()).hexdigest()


def _hash_senha(senha: str) -> str:
    # bcrypt trunca em 72 bytes silenciosamente — o corte é explícito aqui,
    # mesma lição registrada em [012].
    return bcrypt.hashpw(senha.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def _checar_senha(senha: str, hash_: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode("utf-8")[:72], hash_.encode("utf-8"))
    except ValueError:
        return False  # hash malformado no banco vira "senha errada", nunca 500


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
    tem_senha: bool = False
    senha_habilitada: bool = False
    senha_prompt_dispensado: bool = False


def _para_saida(u: User) -> UsuarioOut:
    from app.core.crypto import decifrar

    return UsuarioOut(
        id=u.id,
        nome=u.nome,
        email=u.email,
        cpf=mascarar_cpf(decifrar(u.cpf_cifrado)),
        telefone=u.telefone,
        role=u.role,
        tem_senha=u.senha_hash is not None,
        senha_habilitada=u.senha_habilitada,
        senha_prompt_dispensado=u.senha_prompt_dispensado,
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

    # Regra normal: CPF é único. Exceção: o CPF do próprio dono (superadmin)
    # pode abrir quantas contas ele quiser, para teste — só quem digita o CPF
    # certo (o próprio dono) aciona isto; não é um CPF qualquer que passa a
    # ser reutilizável. O e-mail continua único como sempre.
    indice = indice_deterministico(cpf, "cpf")
    dono_do_cpf = db.execute(
        select(User).where(User.cpf_indice == indice, User.role == "superadmin")
    ).scalar_one_or_none()
    if dono_do_cpf is None and db.execute(select(User).where(User.cpf_indice == indice)).scalar_one_or_none():
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


class SenhaLoginIn(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=200)


@router.post("/login/senha", response_model=UsuarioOut)
def entrar_com_senha(dados: SenhaLoginIn, request: Request, db: Session = Depends(get_db)):
    """[118]: login por senha — opcional, ao lado do código por e-mail. Cai
    dentro do prefixo `/api/v1/auth/login` do nginx (rate limit já existe,
    reaproveitado de graça). "Esqueci a senha" não tem rota própria — pedir
    o código por e-mail de novo já loga direto (fluxo de sempre)."""
    email = dados.email.lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="E-mail não cadastrado. Faça o cadastro primeiro.")

    agora = datetime.now(UTC)
    if user.senha_bloqueada_ate and user.senha_bloqueada_ate > agora:
        minutos = max(1, int((user.senha_bloqueada_ate - agora).total_seconds() // 60) + 1)
        raise HTTPException(
            status_code=429,
            detail=f"Tentativas demais. Tente por código enviado ao e-mail, ou aguarde {minutos} min.",
        )

    if not user.senha_hash or not user.senha_habilitada:
        raise HTTPException(status_code=401, detail="Esta conta não tem senha cadastrada — entre por código.")

    if not _checar_senha(dados.senha, user.senha_hash):
        user.senha_tentativas_falhas += 1
        if user.senha_tentativas_falhas >= MAX_TENTATIVAS_SENHA:
            user.senha_bloqueada_ate = agora + timedelta(minutes=BLOQUEIO_SENHA_MINUTOS)
        db.commit()
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    user.senha_tentativas_falhas = 0
    user.senha_bloqueada_ate = None
    db.commit()

    request.session.clear()  # sessão nova a cada login, contra fixação
    request.session["user_id"] = user.id
    return _para_saida(user)


class SenhaCadastrarIn(BaseModel):
    senha: str = Field(min_length=8, max_length=72)


@router.post("/senha/cadastrar", response_model=UsuarioOut)
def cadastrar_senha(dados: SenhaCadastrarIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Define (ou troca) a senha e liga o login por senha. Sempre autenticado
    — ninguém define senha de outra conta, e definir já prova que a pessoa
    está logada de verdade (por código ou por senha antiga)."""
    user.senha_hash = _hash_senha(dados.senha)
    user.senha_habilitada = True
    user.senha_tentativas_falhas = 0
    user.senha_bloqueada_ate = None
    db.commit()
    db.refresh(user)
    return _para_saida(user)


class SenhaAlternarIn(BaseModel):
    habilitada: bool


@router.post("/senha/alternar", response_model=UsuarioOut)
def alternar_senha(dados: SenhaAlternarIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Liga/desliga o login por senha sem apagar o hash — reativar não pede
    senha de novo. O código por e-mail nunca é desligável (é a base de
    recuperação da conta)."""
    if dados.habilitada and not user.senha_hash:
        raise HTTPException(status_code=422, detail="Cadastre uma senha antes de ligar este método.")
    user.senha_habilitada = dados.habilitada
    db.commit()
    db.refresh(user)
    return _para_saida(user)


@router.post("/senha/dispensar-prompt", response_model=UsuarioOut)
def dispensar_prompt_senha(user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """O aluno disse "agora não" pro convite de cadastrar senha — não insiste
    de novo (o cadastro continua acessível a qualquer momento pelo Perfil)."""
    user.senha_prompt_dispensado = True
    db.commit()
    db.refresh(user)
    return _para_saida(user)
