from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Exam(Base):
    """Uma prova importada (banca, órgão, cargo, ano)."""

    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(primary_key=True)
    banca: Mapped[str] = mapped_column(String(80))
    orgao: Mapped[str] = mapped_column(String(120))
    cargo: Mapped[str] = mapped_column(String(160))
    ano: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    questoes: Mapped[list["Question"]] = relationship(back_populates="exam", cascade="all, delete-orphan")


class Question(Base):
    """Uma questão objetiva. `gabarito` é a resposta oficial (a autoridade — o
    backend corrige por ela, nunca o LLM). `revisada` e `descartada` são o
    controle da tela de revisão; `confianca` guia o que precisa de olho humano."""

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    disciplina: Mapped[str] = mapped_column(String(60), default="")
    enunciado: Mapped[str] = mapped_column(Text)
    gabarito: Mapped[str | None] = mapped_column(String(1), nullable=True)  # A-E; None se o gabarito não casou
    tem_figura: Mapped[bool] = mapped_column(Boolean, default=False)
    modo_exibicao: Mapped[str] = mapped_column(String(10), default="texto")  # texto | imagem
    pagina: Mapped[int] = mapped_column(Integer, default=0)  # página do PDF de origem
    confianca: Mapped[float] = mapped_column(Float, default=1.0)
    aviso: Mapped[str] = mapped_column(String(200), default="")
    revisada: Mapped[bool] = mapped_column(Boolean, default=False)
    descartada: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exam: Mapped[Exam] = relationship(back_populates="questoes")
    alternativas: Mapped[list["Choice"]] = relationship(
        back_populates="questao", cascade="all, delete-orphan", order_by="Choice.letra"
    )


class Choice(Base):
    __tablename__ = "choices"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    letra: Mapped[str] = mapped_column(String(1))  # A-E
    texto: Mapped[str] = mapped_column(Text, default="")

    questao: Mapped[Question] = relationship(back_populates="alternativas")
