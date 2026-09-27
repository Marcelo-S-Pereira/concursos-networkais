from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    """Usuário do sistema. Login por código enviado ao e-mail cadastrado
    (sempre disponível, é a base de recuperação da conta) — desde [118],
    também por senha, opcional (`senha_hash` nulo = sem senha; toggle em
    `senha_habilitada`)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # [118]: login por senha — opcional, ao lado do código por e-mail (que
    # continua sempre disponível e é quem faz "esqueci a senha", sem rota
    # própria — pedir o código de novo já loga direto). `senha_habilitada`
    # é o único toggle real: liga/desliga sem apagar o hash, reativar não
    # pede senha de novo. Tentativas/bloqueio são defesa extra de força
    # bruta, no mesmo espírito do `LoginCode.tentativas`.
    senha_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    senha_habilitada: Mapped[bool] = mapped_column(Boolean, default=False)
    senha_tentativas_falhas: Mapped[int] = mapped_column(Integer, default=0)
    senha_bloqueada_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    senha_prompt_dispensado: Mapped[bool] = mapped_column(Boolean, default=False)

    # CPF cifrado (AES-256-GCM) + índice determinístico para localizar por CPF
    # sem guardar o número em claro. Ver app/core/crypto.py. Não é UNIQUE no
    # banco — a unicidade normal é aplicada em código (auth.py::cadastrar),
    # com a exceção do CPF do próprio superadmin, que pode se repetir em
    # várias contas para ele testar ([102]).
    cpf_cifrado: Mapped[str] = mapped_column(String(255))
    cpf_indice: Mapped[str] = mapped_column(String(64), index=True)

    telefone: Mapped[str] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(32), default="aluno")
    # acesso vitalício: não consome créditos (só o admin liga/desliga, no servidor)
    vitalicio: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    codigos: Mapped[list["LoginCode"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def sem_limites(self) -> bool:
        """Única regra de isenção de limite POR USUÁRIO ([169]): superadmin e
        vitalício. Vale para porta diária de créditos, limite rolante de ritmo e
        cota de recurso (YouTube). Não vale para o teto GLOBAL de orçamento em
        US$ nem para a fila de admissão — esses protegem o bolso e a ambiente de execucao, não
        são limite de pessoa."""
        return self.role == "superadmin" or bool(self.vitalicio)


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
