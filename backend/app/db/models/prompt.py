from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Prompt(Base):
    """[125]: catálogo de prompts do app — a base de dados é a ÚNICA fonte de
    verdade do texto enviado à IA; não existe mais string de prompt fixa no
    código Python. O admin edita `texto` na aba "Prompts" e o novo texto
    passa a ser usado na próxima chamada, sem precisar de deploy.

    `nome`/`onde_usado`/`como_funciona` são metadados descritivos (pra o
    admin entender o que está editando antes de mexer) — também vêm do
    banco, o front nunca chumba essas descrições."""

    __tablename__ = "prompts"

    chave: Mapped[str] = mapped_column(Text, primary_key=True)
    nome: Mapped[str] = mapped_column(Text)
    onde_usado: Mapped[str] = mapped_column(Text)
    como_funciona: Mapped[str] = mapped_column(Text)
    texto: Mapped[str] = mapped_column(Text)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
