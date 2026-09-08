from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemSetting(Base):
    """Configuração simples chave→valor do sistema (ex.: cadastros_bloqueados)."""

    __tablename__ = "system_settings"

    chave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(String(200), default="")
