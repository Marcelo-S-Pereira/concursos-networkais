from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    """Usuário do sistema. Não existe senha em lugar nenhum: o login é por
    código enviado ao e-mail cadastrado."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # CPF cifrado (AES-256-GCM) + índice determinístico para o UNIQUE funcionar
    # sem guardar o número em claro. Ver app/core/crypto.py.
    cpf_cifrado: Mapped[str] = mapped_column(String(255))
    cpf_indice: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    telefone: Mapped[str] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(32), default="aluno")
    # acesso vitalício: não consome créditos (só o admin liga/desliga, no servidor)
    vitalicio: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    codigos: Mapped[list["LoginCode"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class LoginCode(Base):
    """Código de login de uso único enviado por e-mail.

    Guarda o HASH do código, não o código: se o banco vazar, os códigos ainda
    válidos não servem para entrar em conta nenhuma.
    """

    __tablename__ = "login_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    codigo_hash: Mapped[str] = mapped_column(String(64))
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="codigos")
