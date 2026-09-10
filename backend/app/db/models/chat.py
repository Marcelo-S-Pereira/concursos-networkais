from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Conversation(Base):
    """Uma conversa do chat de estudo. Pode estar ligada a um caderno (exam_id)
    ou ser geral (None = todos os cadernos)."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    exam_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    titulo: Mapped[str] = mapped_column(String(200), default="Nova conversa")

    # Qual IA atende esta conversa. None = deixa o motor resolver pela categoria
    # ativa (comportamento padrão); preenchido = o aluno escolheu.
    modelo_texto_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modelo_visao_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Voz (TTS) e transcrição (STT): a escolha já fica salva, mas o motor ainda
    # não executa (cliente.py só fala /chat/completions e /embeddings).
    modelo_voz_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modelo_transcricao_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modo_voz: Mapped[bool] = mapped_column(Boolean, default=False)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    mensagens: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversa", cascade="all, delete-orphan", order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(12))  # user | assistant
    conteudo: Mapped[str] = mapped_column(Text)
    question_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # questão em foco (se houver)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversa: Mapped[Conversation] = relationship(back_populates="mensagens")
