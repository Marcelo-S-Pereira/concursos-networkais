import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import apenas_superadmin, usuario_atual
from app.db.models import Choice, Exam, Question, User
from app.db.session import get_db
from app.modules.creditos import acesso_diario

router = APIRouter(prefix="/exames")
FIGURAS_DIR = Path(__file__).resolve().parents[3].parent / "uploads" / "figuras"


class ChoiceOut(BaseModel):
    letra: str
    texto: str


class QuestaoOut(BaseModel):
    id: int
    numero: int
    pagina: int
    disciplina: str
    enunciado: str
    enunciado_col2: str
    pergunta: str
    gabarito: str | None
    tem_figura: bool
    modo_exibicao: str
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
    excluido_em: datetime | None = None


class ExamPatch(BaseModel):
    banca: str | None = None
    orgao: str | None = None
    cargo: str | None = None
    ano: int | None = None


def _exam_out(ex: Exam) -> ExamOut:
    qs = ex.questoes
    return ExamOut(
        id=ex.id, banca=ex.banca, orgao=ex.orgao, cargo=ex.cargo, ano=ex.ano,
        total=len([q for q in qs if not q.descartada]),
        revisar=len([q for q in qs if q.confianca < 1.0 and not q.revisada and not q.descartada]),
        excluido_em=ex.excluido_em,
    )


class QuestaoPatch(BaseModel):
    enunciado: str | None = None
    enunciado_col2: str | None = None
    pergunta: str | None = None
    gabarito: str | None = None
    disciplina: str | None = None
    alternativas: dict[str, str] | None = None  # {"A": "texto", ...}
    revisada: bool | None = None
    descartada: bool | None = None
    modo_exibicao: str | None = None


def _para_saida(q: Question) -> QuestaoOut:
    return QuestaoOut(
        id=q.id, numero=q.numero, pagina=q.pagina, disciplina=q.disciplina,
        enunciado=q.enunciado, enunciado_col2=q.enunciado_col2, pergunta=q.pergunta,
        gabarito=q.gabarito, tem_figura=q.tem_figura, modo_exibicao=q.modo_exibicao,
        confianca=q.confianca, aviso=q.aviso,
        revisada=q.revisada, descartada=q.descartada,
        alternativas=[ChoiceOut(letra=c.letra, texto=c.texto) for c in q.alternativas],
    )


@router.get("", response_model=list[ExamOut])
def listar_exames(_: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Cadernos ativos (não excluídos)."""
    q = select(Exam).where(Exam.excluido_em.is_(None)).order_by(Exam.id)
    return [_exam_out(ex) for ex in db.execute(q).scalars()]


@router.get("/lixeira", response_model=list[ExamOut])
def listar_lixeira(_: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Cadernos na lixeira, na fila de exclusão permanente (o mais antigo primeiro)."""
    q = select(Exam).where(Exam.excluido_em.is_not(None)).order_by(Exam.excluido_em)
    return [_exam_out(ex) for ex in db.execute(q).scalars()]


@router.get("/{exam_id}/questoes", response_model=list[QuestaoOut])
def listar_questoes(exam_id: int, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Lista as questões de UM caderno — é o que "abrir o acordeão" carrega.
    Atrás da porta diária ([099]): ver quais cadernos existem (`listar_exames`)
    é livre, mas expandir um caderno pra ler as questões já é "usar", e exige
    crédito ([103])."""
    if motivo := acesso_diario.abrir(db, user):
        raise HTTPException(status_code=402, detail=motivo)
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Prova não encontrada.")
    return [_para_saida(q) for q in sorted(exam.questoes, key=lambda q: q.numero)]


@router.patch("/questoes/{qid}", response_model=QuestaoOut)
def editar_questao(qid: int, dados: QuestaoPatch, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")
    if dados.enunciado is not None:
        q.enunciado = dados.enunciado
    if dados.enunciado_col2 is not None:
        q.enunciado_col2 = dados.enunciado_col2
    if dados.pergunta is not None:
        q.pergunta = dados.pergunta
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
    if dados.modo_exibicao is not None:
        if dados.modo_exibicao not in ("texto", "imagem"):
            raise HTTPException(status_code=422, detail="modo_exibicao deve ser 'texto' ou 'imagem'.")
        q.modo_exibicao = dados.modo_exibicao
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
    qid: int, arquivo: UploadFile, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)
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
    tempos: dict[int, int] | None = None  # {question_id: segundos} — opcional


class ResultadoOut(BaseModel):
    total: int
    respondidas: int
    acertos: int
    percentual_bruto: float
    resultado: dict[int, bool]  # {question_id: acertou}
    por_enfase: list[dict]
    tempo_por_enfase: list[dict] = []
    tempo_alvo_s: int | None = None


@router.post("/{exam_id}/corrigir", response_model=ResultadoOut)
def corrigir_simulado(
    exam_id: int, dados: RespostasIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)
):
    """Corrige o cartão-resposta contra o gabarito da base. Só aqui o resultado
    aparece — durante o preenchimento o gabarito nunca é exposto. Modo
    treino/sem tempo — mesma porta diária do simulado cronometrado ([099]);
    faltava aqui, achado no [103]."""
    if motivo := acesso_diario.abrir(db, user):
        raise HTTPException(status_code=402, detail=motivo)
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Prova não encontrada.")
    from app.modules.desempenho.mastery import por_enfase as calc_enfase
    from app.modules.desempenho.mastery import tempo_por_enfase as calc_tempo
    tempos = dados.tempos or {}
    questoes = {q.id: q for q in exam.questoes if not q.descartada}
    resultado: dict[int, bool] = {}
    itens: list[tuple[str, bool]] = []
    itens_tempo: list[tuple[str, int | None]] = []
    acertos = 0
    for qid, questao in questoes.items():
        marcada = dados.respostas.get(qid)
        acertou = marcada is not None and questao.gabarito is not None and marcada.upper() == questao.gabarito
        resultado[qid] = acertou
        itens.append((questao.disciplina, acertou))
        tempo = tempos.get(qid)
        if marcada and tempo is not None:
            itens_tempo.append((questao.disciplina, int(tempo)))
        if acertou:
            acertos += 1
    total = len(questoes)
    return ResultadoOut(
        total=total,
        respondidas=len([qid for qid in questoes if dados.respostas.get(qid)]),
        acertos=acertos,
        percentual_bruto=round(acertos / total * 100, 1) if total else 0.0,
        resultado=resultado,
        por_enfase=calc_enfase(itens),
        tempo_por_enfase=calc_tempo(itens_tempo),
    )


@router.post("/questoes/{qid}/figura/restaurar")
def restaurar_figura(qid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Restaura a página original (desfaz o recorte), copiando o `_original.png`
    de volta para o PNG de exibição."""
    q = db.get(Question, qid)
    if not q or not q.tem_figura:
        raise HTTPException(status_code=404, detail="Sem figura.")
    exibicao = FIGURAS_DIR / f"exam{q.exam_id}_q{q.numero}.png"
    original = FIGURAS_DIR / f"exam{q.exam_id}_q{q.numero}_original.png"
    if not original.exists():
        raise HTTPException(status_code=404, detail="Página original não disponível.")
    shutil.copyfile(original, exibicao)
    return {"ok": True}


@router.get("/{exam_id}/pagina/{n}/imagem")
def pagina_imagem(exam_id: int, n: int, _: User = Depends(apenas_superadmin)):
    """Imagem da página do PDF de origem — para conferir a transcrição."""
    caminho = FIGURAS_DIR / f"exam{exam_id}_pagina{n}.png"
    if not caminho.exists():
        raise HTTPException(status_code=404, detail="Página não renderizada.")
    return FileResponse(caminho, media_type="image/png")


@router.get("/{exam_id}/pagina/{n}/texto")
def pagina_texto(exam_id: int, n: int, _: User = Depends(apenas_superadmin)):
    """Texto extraído da página — selecionável, para copiar e colar nos campos."""
    caminho = FIGURAS_DIR / f"exam{exam_id}_pagina{n}.txt"
    if not caminho.exists():
        raise HTTPException(status_code=404, detail="Texto da página não disponível.")
    return PlainTextResponse(caminho.read_text(encoding="utf-8"))


class TranscricaoOut(BaseModel):
    enunciado: str
    alternativas: dict[str, str]


@router.post("/questoes/{qid}/transcrever", response_model=TranscricaoOut)
def transcrever_com_ia(qid: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Sugere a transcrição da questão usando a IA cadastrada (LLM no texto, VLM
    na figura). NÃO salva — devolve para o usuário revisar e então salvar."""
    from app.modules.ai_registry.cliente import AiCallError
    from app.modules.ai_registry.servico import SemConexaoIA
    from app.modules.ingestion.transcricao_ia import transcrever_questao

    q = db.get(Question, qid)
    if not q:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")
    try:
        dados = transcrever_questao(db, q)
    except SemConexaoIA as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AiCallError as e:
        raise HTTPException(status_code=502, detail=f"A IA falhou: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return TranscricaoOut(**dados)


@router.post("/importar", response_model=ExamOut, status_code=201)
async def importar_caderno(
    prova: UploadFile,
    gabarito: UploadFile,
    banca: str = Form(""),
    orgao: str = Form(""),
    cargo: str = Form(""),
    ano: int | None = Form(None),
    coluna_gabarito: int = Form(0),
    _: User = Depends(apenas_superadmin),
    db: Session = Depends(get_db),
):
    """Importa um caderno novo: salva os PDFs (fora do git) e roda a ingestão."""

    from app.modules.ingestion.servico import ingerir

    if prova.content_type != "application/pdf" or gabarito.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="Envie os dois arquivos em PDF.")

    destino = FIGURAS_DIR.parent / "cadernos"
    destino.mkdir(parents=True, exist_ok=True)
    import uuid

    pid = uuid.uuid4().hex
    caminho_prova = destino / f"{pid}_prova.pdf"
    caminho_gab = destino / f"{pid}_gabarito.pdf"
    dados_prova = await prova.read()
    dados_gab = await gabarito.read()
    if len(dados_prova) > 32_000_000 or len(dados_gab) > 32_000_000:
        raise HTTPException(status_code=413, detail="PDF grande demais (máx 32MB cada).")
    caminho_prova.write_bytes(dados_prova)
    caminho_gab.write_bytes(dados_gab)

    try:
        exam = ingerir(
            db, caminho_prova=str(caminho_prova), caminho_gabarito=str(caminho_gab),
            banca=banca or "?", orgao=orgao or "?", cargo=cargo or "?", ano=ano,
            coluna_gabarito=coluna_gabarito,
        )
    except Exception as e:  # noqa: BLE001 - devolve erro legível ao usuário
        raise HTTPException(status_code=422, detail=f"Falha ao importar: {e}") from e

    qs = [q for q in exam.questoes if not q.descartada]
    return ExamOut(
        id=exam.id, banca=exam.banca, orgao=exam.orgao, cargo=exam.cargo, ano=exam.ano,
        total=len(qs), revisar=len([q for q in qs if q.confianca < 1.0 and not q.revisada]),
    )


@router.patch("/{exam_id}", response_model=ExamOut)
def editar_caderno(exam_id: int, dados: ExamPatch, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Edita os dados mestre do caderno (banca/órgão/cargo/ano)."""
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Caderno não encontrado.")
    if dados.banca is not None:
        exam.banca = dados.banca.strip() or exam.banca
    if dados.orgao is not None:
        exam.orgao = dados.orgao.strip() or exam.orgao
    if dados.cargo is not None:
        exam.cargo = dados.cargo.strip() or exam.cargo
    if dados.ano is not None:
        exam.ano = dados.ano
    db.commit()
    db.refresh(exam)
    return _exam_out(exam)


@router.delete("/{exam_id}", status_code=204)
def apagar_caderno(exam_id: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Exclusão SUAVE: o caderno vai para a lixeira, não some da base."""
    exam = db.get(Exam, exam_id)
    if exam and exam.excluido_em is None:
        exam.excluido_em = datetime.now(UTC)
        db.commit()


@router.post("/{exam_id}/restaurar", response_model=ExamOut)
def restaurar_caderno(exam_id: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Tira o caderno da lixeira e o devolve à lista de ativos."""
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Caderno não encontrado.")
    exam.excluido_em = None
    db.commit()
    db.refresh(exam)
    return _exam_out(exam)


@router.delete("/{exam_id}/permanente", status_code=204)
def apagar_permanente(exam_id: int, _: User = Depends(apenas_superadmin), db: Session = Depends(get_db)):
    """Exclusão DEFINITIVA — só de caderno que já está na lixeira. Sem volta."""
    exam = db.get(Exam, exam_id)
    if not exam:
        return
    if exam.excluido_em is None:
        raise HTTPException(status_code=409, detail="Mande o caderno para a lixeira antes de excluir em definitivo.")
    db.delete(exam)
    db.commit()


class ExplicarIn(BaseModel):
    student_answer: str | None = None


@router.post("/questoes/{qid}/explicar")
def explicar(qid: int, dados: ExplicarIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Tutor IA: explica a questão (diagnóstico, mini-aula, macete). Só pedagogia;
    o gabarito/correção já vêm do backend. Atrás da porta diária ([099]) —
    chama a IA de verdade, faltava o gate aqui, achado no [103]."""
    if motivo := acesso_diario.abrir(db, user):
        raise HTTPException(status_code=402, detail=motivo)
    from app.modules.ai_registry.cliente import AiCallError
    from app.modules.ai_registry.servico import SemConexaoIA
    from app.modules.tutor.tutor import explicar_questao

    q = db.get(Question, qid)
    if not q:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")
    try:
        return explicar_questao(db, q, user.id, dados.student_answer)
    except SemConexaoIA as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (AiCallError, ValueError) as e:
        raise HTTPException(status_code=502, detail=f"A IA falhou: {e}") from e


class GemeaOut(BaseModel):
    id: int
    enunciado: str
    alternativas: dict[str, str]


@router.post("/questoes/{qid}/gemeas", response_model=list[GemeaOut])
def gerar_gemeas_rota(qid: int, user: User = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Gera 2 questões gêmeas (IA) para praticar o mesmo conceito. Gabarito não
    é exposto aqui — o aluno responde primeiro. Atrás da porta diária ([099]) —
    chama a IA de verdade, faltava o gate aqui, achado no [103]."""
    if motivo := acesso_diario.abrir(db, user):
        raise HTTPException(status_code=402, detail=motivo)
    from app.modules.ai_registry.cliente import AiCallError
    from app.modules.ai_registry.servico import SemConexaoIA
    from app.modules.tutor.gemeas import gerar_gemeas

    q = db.get(Question, qid)
    if not q:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")
    try:
        return gerar_gemeas(db, q, user.id)
    except SemConexaoIA as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (AiCallError, ValueError) as e:
        raise HTTPException(status_code=502, detail=f"A IA falhou: {e}") from e


class GemeaRespostaIn(BaseModel):
    letra: str


@router.post("/gemeas/{twin_id}/responder")
def responder_gemea(
    twin_id: int, dados: GemeaRespostaIn, user: User = Depends(usuario_atual), db: Session = Depends(get_db)
):
    """Corrige a gêmea contra o gabarito que a própria IA gerou para ela."""
    from app.db.models import TwinQuestion

    tw = db.get(TwinQuestion, twin_id)
    if not tw or tw.user_id != user.id:
        raise HTTPException(status_code=404, detail="Gêmea não encontrada.")
    acertou = dados.letra.upper() == tw.gabarito
    return {"acertou": acertou, "gabarito": tw.gabarito}
