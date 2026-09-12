from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Conversation(Base):
    """Uma conversa do chat de estudo — ou do Tutor IA ([109]), que reaproveita
    esta mesma tabela e o mesmo pipeline de crédito/voz/modelo, só mudando o
    system prompt e o filtro de RAG (`modo`). Pode estar ligada a um caderno
    (exam_id) ou ser geral (None = todos os cadernos, ou sem caderno no Tutor)."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    exam_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # [115]: lista de cadernos (substitui exam_id pra conversas novas — o
    # singular fica só por retrocompatibilidade de leitura das antigas).
    # Vazio = sem caderno específico (mesmo comportamento de exam_id=None).
    exam_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    # [115]: "normal" (aluno escolhe a questão) | "random" (backend sorteia
    # entre os exam_ids da conversa).
    modo_questao: Mapped[str] = mapped_column(String(10), default="normal")
    titulo: Mapped[str] = mapped_column(String(200), default="Nova conversa")
    # [109]: "chat" (tutor do caderno) | "tutor" (especialista geral, RAG uso=tutor).
    modo: Mapped[str] = mapped_column(String(10), default="chat")
    # [109]: só usado no modo "tutor" — tom da resposta, escolhido pelo usuário.
    persona: Mapped[str] = mapped_column(String(10), default="professor")
    # [110]: ids de RagDocument escolhidos pra grounding desta conversa
    # (só modo "tutor"). Vazio = usa todos os uso_tutor=true (padrão de antes).
    rag_doc_ids: Mapped[list[int]] = mapped_column(JSON, default=list)

    # Qual IA atende esta conversa. None = deixa o motor resolver pela categoria
    # ativa (comportamento padrão); preenchido = o aluno escolheu.
    modelo_texto_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modelo_visao_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Voz (TTS) e transcrição (STT) — o motor executa de verdade desde o [095].
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
