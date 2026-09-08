"""Estatística pública por SUBTEMA do edital, por caderno (spec §9).

Cada caderno tem seus subtemas (do conteúdo programático do edital, extraídos por
IA ou manuais), agrupados por disciplina; o admin preenche o % de acerto público
de cada subtema. Sem inventar — sem dado, fica em branco.
"""

from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import apenas_superadmin
from app.db.models import EmphasisPublicStat, Exam, Tema, User
from app.db.session import get_db

router = APIRouter(prefix="/estatisticas/enfase")


class StatIn(BaseModel):
    exam_id: int | None = None
    disciplina: str = ""
    banca: str = ""
    orgao: str = ""
    cargo: str = ""
    ano: int | None = None
    enfase: str
    amostra: int | None = None
    acerto_pct: float | None = None
    fonte: str = ""
    tipo_fonte: str = ""
    status: str = "OK"


class StatOut(StatIn):
    id: int


def _saida(x: EmphasisPublicStat) -> StatOut:
    return StatOut(
        id=x.id, exam_id=x.exam_id, disciplina=x.disciplina, banca=x.banca, orgao=x.orgao,
        cargo=x.cargo, ano=x.ano, enfase=x.enfase, amostra=x.amostra, acerto_pct=x.acerto_pct,
        fonte=x.fonte, tipo_fonte=x.tipo_fonte, status=x.status,
    )


# ─────────── estrutura por caderno (disciplinas → subtemas + stat) ───────────
class TemaComStat(BaseModel):
    id: int
    nome: str
    stat: StatOut | None


class DisciplinaEstrutura(BaseModel):
    disciplina: str
    temas: list[TemaComStat]


class EstruturaOut(BaseModel):
    exam_id: int
    cargo: str
    disciplinas: list[DisciplinaEstrutura]


@router.get("/estrutura", response_model=EstruturaOut)
def estrutura(exam_id: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Caderno não encontrado.")
    temas = list(
        db.execute(
            select(Tema).where(Tema.exam_id == exam_id).order_by(Tema.disciplina, Tema.ordem, Tema.id)
        ).scalars()
    )
    stats = {
        (s.disciplina, s.enfase): s
        for s in db.execute(select(EmphasisPublicStat).where(EmphasisPublicStat.exam_id == exam_id)).scalars()
    }
    grupos: OrderedDict[str, list[Tema]] = OrderedDict()
    for t in temas:
        grupos.setdefault(t.disciplina, []).append(t)
    discs = [
        DisciplinaEstrutura(
            disciplina=disc,
            temas=[
                TemaComStat(id=t.id, nome=t.nome,
                            stat=_saida(stats[(disc, t.nome)]) if (disc, t.nome) in stats else None)
                for t in lista
            ],
        )
        for disc, lista in grupos.items()
    ]
    return EstruturaOut(exam_id=exam_id, cargo=exam.cargo, disciplinas=discs)


@router.post("/temas/extrair")
def extrair(exam_id: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Lê o conteúdo programático do edital (RAG) e cria os subtemas por disciplina (IA)."""
    from app.modules.ai_registry.cliente import AiCallError
    from app.modules.ai_registry.servico import SemConexaoIA
    from app.modules.estatistica.temas_edital import extrair_subtemas

    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Caderno não encontrado.")
    try:
        mapa = extrair_subtemas(db, exam.cargo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SemConexaoIA as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AiCallError as e:
        raise HTTPException(status_code=502, detail=f"IA falhou: {e}") from e

    criados = 0
    for disciplina, nomes in mapa.items():
        existentes = {
            t.nome for t in db.execute(
                select(Tema).where(Tema.exam_id == exam_id, Tema.disciplina == disciplina)
            ).scalars()
        }
        for i, nome in enumerate(nomes):
            if nome not in existentes:
                db.add(Tema(exam_id=exam_id, disciplina=disciplina, nome=nome, ordem=i))
                criados += 1
    db.commit()
    return {"criados": criados, "disciplinas": list(mapa.keys())}


class TemaIn(BaseModel):
    exam_id: int
    disciplina: str
    nome: str


@router.post("/temas")
def add_tema(dados: TemaIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    if not dados.nome.strip() or not dados.disciplina.strip():
        raise HTTPException(status_code=422, detail="Disciplina e nome do subtema são obrigatórios.")
    t = Tema(exam_id=dados.exam_id, disciplina=dados.disciplina.strip(), nome=dados.nome.strip(), ordem=999)
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id, "disciplina": t.disciplina, "nome": t.nome}


@router.delete("/temas/{tid}", status_code=204)
def del_tema(tid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    t = db.get(Tema, tid)
    if t:
        db.delete(t)
        db.commit()


@router.put("/por-tema", response_model=StatOut)
def upsert_tema(dados: StatIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Grava a estatística de um subtema (chaveada por caderno + subtema)."""
    if not dados.enfase.strip():
        raise HTTPException(status_code=422, detail="Subtema é obrigatório.")
    q = select(EmphasisPublicStat).where(EmphasisPublicStat.enfase == dados.enfase)
    q = q.where(EmphasisPublicStat.exam_id == dados.exam_id) if dados.exam_id is not None \
        else q.where(EmphasisPublicStat.exam_id.is_(None))
    x = db.execute(q).scalars().first()
    if x:
        for campo, valor in dados.model_dump().items():
            setattr(x, campo, valor)
    else:
        x = EmphasisPublicStat(**dados.model_dump())
        db.add(x)
    db.commit()
    db.refresh(x)
    return _saida(x)


# ─────────── CRUD antigo (compatibilidade) ───────────
@router.get("", response_model=list[StatOut])
def listar(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    return [_saida(x) for x in db.execute(select(EmphasisPublicStat).order_by(EmphasisPublicStat.enfase)).scalars()]


@router.post("", response_model=StatOut, status_code=201)
def criar(dados: StatIn, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    x = EmphasisPublicStat(**dados.model_dump())
    db.add(x)
    db.commit()
    db.refresh(x)
    return _saida(x)


@router.delete("/{sid}", status_code=204)
def apagar(sid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    x = db.get(EmphasisPublicStat, sid)
    if x:
        db.delete(x)
        db.commit()
