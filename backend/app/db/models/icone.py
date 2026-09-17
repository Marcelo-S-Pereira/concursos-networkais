from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ComponentIcon(Base):
    """[128]: qual ícone o admin escolheu para cada "slot" de botão do app —
    sem linha = usa o texto padrão (comportamento de hoje). `tipo`
    "biblioteca" (nome de um ícone curado, `iconesBiblioteca.tsx` no front) ou
    "upload" (arquivo próprio, em `uploads/icones/`, servido por rota
    autenticada). O catálogo fixo dos slots que existem vive em código
    (`app/modules/icones/catalogo.py`), não no banco — isto aqui só guarda a
    ESCOLHA feita para cada um."""

    __tablename__ = "component_icons"

    slot: Mapped[str] = mapped_column(Text, primary_key=True)
    tipo: Mapped[str] = mapped_column(Text)
    valor: Mapped[str] = mapped_column(Text)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
