from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Tema(Base):
    """Subtema do conteúdo programático de um caderno (ex.: Português → 'Crase').

    Lista canônica por (exam_id, disciplina) — vem do edital (IA) ou entrada manual.
    A estatística pública (EmphasisPublicStat) é preenchida por subtema.
    """

    __tablename__ = "temas"

    id: Mapped[int] = mapped_column(primary_key=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    disciplina: Mapped[str] = mapped_column(String(120), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    ordem: Mapped[int] = mapped_column(Integer, default=0)
