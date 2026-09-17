"""Revisão espaçada do aluno (spec §17). O backend corrige pelo gabarito."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import usuario_atual
from app.api.v1.questoes import QuestaoOut, _para_saida
from app.db.models import Question, ReviewSchedule, User
from app.db.session import get_db
from app.modules.desempenho.revisao import responder_revisao

router = APIRouter(prefix="/revisao")


class QuestaoRevisaoOut(QuestaoOut):
    # [153]: "simulado" ou "chat" — de onde veio o erro que pôs esta questão
    # na fila, pro aluno saber se foi engano no Simulado ou no Chat de estudo.
    origem: str = "simulado"


@router.get("", response_model=list[QuestaoRevisaoOut])
def devidas(user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Questões cuja revisão vence hoje (ou já venceu)."""
    agora = datetime.now(UTC)
    origens = dict(db.execute(
        select(ReviewSchedule.question_id, ReviewSchedule.origem).where(
            ReviewSchedule.user_id == user.id, ReviewSchedule.vence_em <= agora
        )
    ).all())
    if not origens:
        return []
    questoes = db.execute(
        select(Question).where(Question.id.in_(origens.keys()), ~Question.descartada)
    ).scalars()
    return [
        QuestaoRevisaoOut(**_para_saida(q).model_dump(), origem=origens.get(q.id, "simulado"))
        for q in questoes
    ]


class RespostaIn(BaseModel):
    letra: str


class RespostaOut(BaseModel):
    acertou: bool


@router.post("/{qid}/responder", response_model=RespostaOut)
def responder(qid: int, dados: RespostaIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")
    acertou = bool(q.gabarito and dados.letra.upper() == q.gabarito)
    responder_revisao(db, user.id, qid, acertou)
    db.commit()
    return RespostaOut(acertou=acertou)
