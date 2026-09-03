"""Ingestão: PDF da prova + PDF do gabarito → questões no banco.

- extrai o texto nativo (pypdf);
- parseia as questões (prova_parser) e o gabarito ciente de colunas (gabarito_parser);
- casa o gabarito por número;
- renderiza a página das questões com figura para PNG (pypdfium2), guardado em
  uploads/figuras (fora do git), referenciado por caminho;
- grava exam + questions + choices com confiança e avisos.
O backend é o dono do gabarito (autoridade). Nada aqui chama LLM.
"""

import re
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.db.models import Choice, Exam, Question
from app.modules.ingestion.gabarito_parser import parse_respostas
from app.modules.ingestion.prova_parser import parse_prova

RUIDO = re.compile(r"pcimarkpci|pciconcursos")
# backend/app/modules/ingestion/servico.py → parents[3] = backend → .parent = raiz do projeto
FIGURAS_DIR = Path(__file__).resolve().parents[3].parent / "uploads" / "figuras"


def _texto_paginas(caminho: str) -> list[str]:
    r = PdfReader(caminho)
    return [(p.extract_text() or "") for p in r.pages]


def _texto_limpo(paginas: list[str]) -> str:
    linhas = []
    for pg in paginas:
        for ln in pg.split("\n"):
            if not RUIDO.search(ln):
                linhas.append(ln)
    return "\n".join(linhas)


def _renderizar_pagina(caminho_pdf: str, pagina: int, destino: Path) -> None:
    """Renderiza a página para o PNG de exibição E guarda um `_original.png`
    ao lado (nunca sobrescrito pelo recorte) para o botão Restaurar."""
    pdf = pdfium.PdfDocument(caminho_pdf)
    try:
        img = pdf[pagina].render(scale=2).to_pil()
        destino.parent.mkdir(parents=True, exist_ok=True)
        img.save(destino)
        img.save(destino.with_name(destino.stem + "_original.png"))
    finally:
        pdf.close()


def ingerir(
    db: Session,
    *,
    caminho_prova: str,
    caminho_gabarito: str,
    banca: str,
    orgao: str,
    cargo: str,
    ano: int | None,
    coluna_gabarito: int = 0,
    disciplinas: dict[int, str] | None = None,
) -> Exam:
    paginas_prova = _texto_paginas(caminho_prova)
    questoes = parse_prova(paginas_prova)

    gab_texto = _texto_limpo(_texto_paginas(caminho_gabarito))
    respostas = parse_respostas(gab_texto, coluna_alvo=coluna_gabarito)

    exam = Exam(banca=banca, orgao=orgao, cargo=cargo, ano=ano)
    db.add(exam)
    db.flush()  # gera exam.id

    disciplinas = disciplinas or {}
    for q in questoes:
        gabarito = respostas.get(q.numero)
        aviso = q.aviso
        confianca = q.confianca
        if gabarito is None:
            confianca = min(confianca, 0.5)
            aviso = (aviso + "; " if aviso else "") + "gabarito não encontrado"

        figura_path = ""
        if q.tem_figura:
            destino = FIGURAS_DIR / f"exam{exam.id}_q{q.numero}.png"
            try:
                _renderizar_pagina(caminho_prova, q.pagina, destino)
                figura_path = f"q{q.numero}"  # marcador; o arquivo real fica fora do git
            except Exception as e:  # noqa: BLE001 - render de figura é best-effort
                aviso = (aviso + "; " if aviso else "") + f"falha ao renderizar figura: {e}"

        questao = Question(
            exam_id=exam.id,
            numero=q.numero,
            disciplina=disciplinas.get(q.numero, ""),
            enunciado=q.enunciado + (f"\n[figura: {figura_path}]" if figura_path else ""),
            gabarito=gabarito,
            tem_figura=q.tem_figura,
            confianca=confianca,
            aviso=aviso[:200],
        )
        db.add(questao)
        db.flush()
        for letra, texto in sorted(q.alternativas.items()):
            db.add(Choice(question_id=questao.id, letra=letra, texto=texto))

    db.commit()
    db.refresh(exam)
    return exam
