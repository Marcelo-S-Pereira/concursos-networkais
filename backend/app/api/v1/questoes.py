from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import usuario_atual
from app.db.models import Choice, Exam, Question, User
from app.db.session import get_db

router = APIRouter(prefix="/exames")
FIGURAS_DIR = Path(__file__).resolve().parents[3].parent / "uploads" / "figuras"


class ChoiceOut(BaseModel):
    letra: str
    texto: str


class QuestaoOut(BaseModel):
    id: int
    numero: int
    disciplina: str
    enunciado: str
    gabarito: str | None
    tem_figura: bool
    confianca: float
    aviso: str
    revisada: bool
    descartada: bool
    alternativas: list[ChoiceOut]


class ExamOut(BaseModel):
    id: int
    banca: str
    orgao: str
    cargo: str
    ano: int | None
    total: int
    revisar: int


class QuestaoPatch(BaseModel):
    enunciado: str | None = None
    gabarito: str | None = None
    disciplina: str | None = None
    alternativas: dict[str, str] | None = None  # {"A": "texto", ...}
    revisada: bool | None = None
    descartada: bool | None = None


def _para_saida(q: Question) -> QuestaoOut:
    return QuestaoOut(
        id=q.id, numero=q.numero, disciplina=q.disciplina, enunciado=q.enunciado,
        gabarito=q.gabarito, tem_figura=q.tem_figura, confianca=q.confianca, aviso=q.aviso,
        revisada=q.revisada, descartada=q.descartada,
        alternativas=[ChoiceOut(letra=c.letra, texto=c.texto) for c in q.alternativas],
    )


@router.get("", response_model=list[ExamOut])
def listar_exames(_: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    saida = []
    for ex in db.execute(select(Exam).order_by(Exam.id)).scalars():
        qs = ex.questoes
        saida.append(ExamOut(id=ex.id, banca=ex.banca, orgao=ex.orgao, cargo=ex.cargo, ano=ex.ano,
                             total=len([q for q in qs if not q.descartada]),
                             revisar=len([q for q in qs if q.confianca < 1.0 and not q.revisada and not q.descartada])))
    return saida


@router.get("/{exam_id}/questoes", response_model=list[QuestaoOut])
def listar_questoes(exam_id: int, _: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Prova não encontrada.")
    return [_para_saida(q) for q in sorted(exam.questoes, key=lambda q: q.numero)]


@router.patch("/questoes/{qid}", response_model=QuestaoOut)
def editar_questao(qid: int, dados: QuestaoPatch, _: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")
    if dados.enunciado is not None:
        q.enunciado = dados.enunciado
    if dados.disciplina is not None:
        q.disciplina = dados.disciplina
    if dados.gabarito is not None:
        letra = dados.gabarito.strip().upper()
        if letra not in {"A", "B", "C", "D", "E", ""}:
            raise HTTPException(status_code=422, detail="Gabarito deve ser A-E.")
        q.gabarito = letra or None
    if dados.alternativas is not None:
        por_letra = {c.letra: c for c in q.alternativas}
        for letra, texto in dados.alternativas.items():
            L = letra.strip().upper()
            if L in por_letra:
                por_letra[L].texto = texto
            elif L in {"A", "B", "C", "D", "E"}:
                db.add(Choice(question_id=q.id, letra=L, texto=texto))
    if dados.revisada is not None:
        q.revisada = dados.revisada
        if dados.revisada:
            q.confianca = 1.0  # revisão humana zera a dúvida
    if dados.descartada is not None:
        q.descartada = dados.descartada
    db.commit()
    db.refresh(q)
    return _para_saida(q)


@router.get("/questoes/{qid}/figura")
def figura(qid: int, _: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    q = db.get(Question, qid)
    if not q or not q.tem_figura:
        raise HTTPException(status_code=404, detail="Sem figura.")
    caminho = FIGURAS_DIR / f"exam{q.exam_id}_q{q.numero}.png"
    if not caminho.exists():
        raise HTTPException(status_code=404, detail="Imagem não encontrada.")
    return FileResponse(caminho, media_type="image/png")


@router.post("/questoes/{qid}/figura")
async def salvar_figura(
    qid: int, arquivo: UploadFile, _: User = Depends(usuario_atual), db: Session = Depends(get_db)
):
    """Recebe o RECORTE (PNG) feito na tela e o integra à questão como figura."""
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")
    if arquivo.content_type not in ("image/png", "image/jpeg"):
        raise HTTPException(status_code=422, detail="Envie uma imagem PNG ou JPEG.")
    conteudo = await arquivo.read()
    if len(conteudo) > 5_000_000:
        raise HTTPException(status_code=413, detail="Imagem grande demais (máx 5MB).")
    FIGURAS_DIR.mkdir(parents=True, exist_ok=True)
    destino = FIGURAS_DIR / f"exam{q.exam_id}_q{q.numero}.png"
    destino.write_bytes(conteudo)
    q.tem_figura = True
    db.commit()
    return {"ok": True}


class RespostasIn(BaseModel):
    respostas: dict[int, str]  # {question_id: "A".."E"}


class ResultadoOut(BaseModel):
    total: int
    respondidas: int
    acertos: int
    resultado: dict[int, bool]  # {question_id: acertou}


@router.post("/{exam_id}/corrigir", response_model=ResultadoOut)
def corrigir_simulado(
    exam_id: int, dados: RespostasIn, _: User = Depends(usuario_atual), db: Session = Depends(get_db)
):
    """Corrige o cartão-resposta contra o gabarito da base. Só aqui o resultado
    aparece — durante o preenchimento o gabarito nunca é exposto."""
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Prova não encontrada.")
    questoes = {q.id: q for q in exam.questoes if not q.descartada}
    resultado: dict[int, bool] = {}
    acertos = 0
    for qid, questao in questoes.items():
        marcada = dados.respostas.get(qid)
        acertou = marcada is not None and questao.gabarito is not None and marcada.upper() == questao.gabarito
        resultado[qid] = acertou
        if acertou:
            acertos += 1
    return ResultadoOut(
        total=len(questoes),
        respondidas=len([qid for qid in questoes if dados.respostas.get(qid)]),
        acertos=acertos,
        resultado=resultado,
    )
