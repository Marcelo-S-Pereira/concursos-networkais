"""Simulado por tempo. O backend é dono do relógio (spec §6): define o prazo e
recusa a finalização depois dele como 'no prazo'. A correção usa o gabarito da
base — nunca exposto antes do fim."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import usuario_atual
from app.db.models import EmphasisPublicStat, Exam, ExamRules, SimulationAnswer, SimulationRun, User
from app.db.session import get_db
from app.modules.desempenho.mastery import por_enfase, rotulo_delta
from app.modules.desempenho.mastery import tempo_por_enfase as calc_tempo_enfase
from app.modules.desempenho.revisao import agendar_erro

router = APIRouter(prefix="/simulado")


class IniciarIn(BaseModel):
    exam_id: int
    duration_seconds: int = Field(ge=30, le=6 * 3600)


class RunOut(BaseModel):
    simulation_id: int
    started_at: datetime
    deadline_at: datetime
    duration_seconds: int
    question_count: int
    status: str


class EntregarIn(BaseModel):
    respostas: dict[int, str]  # {question_id: "A".."E"}
    tempos: dict[int, int] | None = None  # {question_id: segundos} — opcional


class ResultadoOut(BaseModel):
    acertos: int
    total: int
    respondidas: int
    em_branco: int
    percentual_bruto: float
    encerrado_no_prazo: bool
    resultado: dict[int, bool]
    por_enfase: list[dict]
    classificacao: dict | None
    tempo_por_enfase: list[dict] = []
    tempo_alvo_s: int | None = None


@router.post("/iniciar", response_model=RunOut)
def iniciar(dados: IniciarIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    exam = db.get(Exam, dados.exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Prova não encontrada.")
    n = len([q for q in exam.questoes if not q.descartada])
    agora = datetime.now(UTC)
    run = SimulationRun(
        exam_id=exam.id, user_id=user.id, started_at=agora,
        deadline_at=agora + timedelta(seconds=dados.duration_seconds),
        duration_seconds=dados.duration_seconds, question_count=n, status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return RunOut(
        simulation_id=run.id, started_at=run.started_at, deadline_at=run.deadline_at,
        duration_seconds=run.duration_seconds, question_count=run.question_count, status=run.status,
    )


@router.post("/{run_id}/entregar", response_model=ResultadoOut)
def entregar(run_id: int, dados: EntregarIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    run = db.get(SimulationRun, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="Simulado não encontrado.")
    if run.status == "finished":
        raise HTTPException(status_code=409, detail="Este simulado já foi encerrado.")

    agora = datetime.now(UTC)
    no_prazo = agora <= run.deadline_at

    exam = db.get(Exam, run.exam_id)
    questoes = {q.id: q for q in exam.questoes if not q.descartada}
    tempos = dados.tempos or {}
    resultado: dict[int, bool] = {}
    itens_enfase: list[tuple[str, bool]] = []
    itens_tempo: list[tuple[str, int | None]] = []
    acertos = respondidas = 0
    for qid, q in questoes.items():
        letra = (dados.respostas.get(qid) or "").upper() or None
        if letra:
            respondidas += 1
        correta = bool(letra and q.gabarito and letra == q.gabarito)
        resultado[qid] = correta
        if correta:
            acertos += 1
        itens_enfase.append((q.disciplina, correta))
        tempo = tempos.get(qid)
        if letra and tempo is not None:  # só conta o tempo de questão respondida
            itens_tempo.append((q.disciplina, int(tempo)))
        if not correta:
            agendar_erro(db, user.id, qid)
        db.add(SimulationAnswer(run_id=run.id, question_id=qid, letra=letra, correta=correta,
                                tempo_resposta_s=int(tempo) if tempo is not None else None))

    run.status = "finished"
    run.acertos = acertos
    run.finished_at = agora
    db.commit()

    total = len(questoes)
    enfases = por_enfase(itens_enfase)
    tempos_enfase = calc_tempo_enfase(itens_tempo)
    tempo_alvo = round(run.duration_seconds / run.question_count) if run.question_count else None
    _anexar_historico(db, exam, enfases)

    from sqlalchemy import select
    regras = db.execute(select(ExamRules).where(ExamRules.exam_id == exam.id)).scalar_one_or_none()
    classificacao = None
    if regras:
        from app.modules.desempenho.classificacao import classificar
        from app.modules.desempenho.ranking import estimar_ranking
        classificacao = classificar(regras, itens_enfase)
        classificacao["ranking"] = estimar_ranking(db, exam, itens_enfase, regras)

    return ResultadoOut(
        acertos=acertos, total=total, respondidas=respondidas, em_branco=total - respondidas,
        percentual_bruto=round(acertos / total * 100, 1) if total else 0.0,
        encerrado_no_prazo=no_prazo, resultado=resultado, por_enfase=enfases,
        classificacao=classificacao,
        tempo_por_enfase=tempos_enfase, tempo_alvo_s=tempo_alvo,
    )


def _anexar_historico(db: Session, exam: Exam, enfases: list[dict]) -> None:
    """Para cada ênfase, busca a estatística pública mais aderente (mesma banca/
    órgão/cargo primeiro; senão só a ênfase) e calcula o delta (spec §10). Sem
    dado: marca PUBLIC_DATA_NOT_FOUND — nunca inventa."""
    from sqlalchemy import select
    for e in enfases:
        stat = db.execute(
            select(EmphasisPublicStat).where(
                EmphasisPublicStat.enfase == e["enfase"],
                EmphasisPublicStat.banca == exam.banca,
                EmphasisPublicStat.cargo == exam.cargo,
            )
        ).scalars().first()
        if not stat:
            stat = db.execute(
                select(EmphasisPublicStat).where(EmphasisPublicStat.enfase == e["enfase"])
            ).scalars().first()
        if stat and stat.acerto_pct is not None and stat.status == "OK":
            delta = round(e["percentual"] - stat.acerto_pct, 1)
            e["historico_pct"] = stat.acerto_pct
            e["amostra_historico"] = stat.amostra
            e["delta"] = delta
            e["delta_rotulo"] = rotulo_delta(delta)
            e["fonte"] = stat.fonte
        else:
            e["historico_pct"] = None
            e["delta"] = None
            e["status_historico"] = "PUBLIC_DATA_NOT_FOUND"
