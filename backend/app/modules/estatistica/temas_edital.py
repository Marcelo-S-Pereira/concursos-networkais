"""Extrai os SUBTEMAS do conteúdo programático do edital, por disciplina, via IA.

O edital já está indexado no RAG; pegamos o texto do conteúdo programático e o LLM
devolve {disciplina: [subtemas]}. Nunca inventa — usa só o que está no texto.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RagChunk, RagDocument

SISTEMA = (
    "Você extrai os SUBTEMAS do conteúdo programático de um edital de concurso, "
    "agrupados por disciplina. Devolva SOMENTE um JSON no formato "
    '{"Língua Portuguesa": ["...", "..."], "Matemática": ["..."], '
    '"Conhecimentos Específicos": ["..."]}. Cada subtema é uma string curta (ex.: '
    '"Concordância nominal e verbal", "Crase", "Análise combinatória"). Para '
    "Conhecimentos Específicos, use os subtemas do CARGO indicado. Não invente: use "
    "apenas o que está no texto do edital."
)


def _texto_conteudo_programatico(db: Session) -> str:
    doc = db.execute(
        select(RagDocument).where(RagDocument.colecao == "oficial").order_by(RagDocument.id)
    ).scalars().first()
    if not doc:
        return ""
    chunks = db.execute(
        select(RagChunk).where(RagChunk.document_id == doc.id).order_by(RagChunk.chunk_index)
    ).scalars().all()
    texto = "\n".join(c.conteudo for c in chunks)
    up = texto.upper()
    # o Anexo IV (conteúdo programático de verdade) fica perto do FIM do edital;
    # a 1ª menção a "CONTEÚDOS PROGRAMÁTICOS" costuma ser só uma referência. rfind.
    alvo = up.rfind("ANEXO IV")
    if alvo < 0:
        alvo = up.rfind("CONTEÚDOS PROGRAMÁTICOS")
    if alvo < 0:
        alvo = up.rfind("CONTEUDOS PROGRAMATICOS")
    trecho = texto[alvo:] if alvo >= 0 else texto
    return trecho[:26000]  # cobre básicos + específicos de vários cargos


def extrair_subtemas(db: Session, cargo: str) -> dict[str, list[str]]:
    from app.modules.ai_registry import servico
    from app.modules.ingestion.transcricao_ia import _parse_json_tolerante

    texto = _texto_conteudo_programatico(db)
    if not texto.strip():
        raise ValueError("Edital não indexado. Importe e indexe o edital na Biblioteca antes.")

    resposta = servico.conversar(
        db, "texto",
        [{"role": "system", "content": SISTEMA},
         {"role": "user", "content": f"Cargo: {cargo}\n\nConteúdo programático do edital:\n{texto}"}],
        origem="extrair_subtemas", max_tokens=1500,
    )
    dados = _parse_json_tolerante(resposta) or {}
    saida: dict[str, list[str]] = {}
    for disciplina, lista in dados.items():
        if isinstance(lista, list):
            nomes = [str(s).strip() for s in lista if str(s).strip()]
            if nomes:
                saida[str(disciplina).strip()] = nomes
    return saida
