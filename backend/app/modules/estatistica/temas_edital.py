"""Extrai os SUBTEMAS do conteúdo programático do edital, por disciplina, via IA.

O edital já está indexado no RAG; pegamos o texto do conteúdo programático e o LLM
devolve {disciplina: [subtemas]}. Nunca inventa — usa só o que está no texto.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RagChunk, RagDocument

# [125]: texto em `prompts` (chave "temas_edital_sistema"), não mais aqui.


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
    from app.modules.prompts import prompts

    texto = _texto_conteudo_programatico(db)
    if not texto.strip():
        raise ValueError("Edital não indexado. Importe e indexe o edital na Biblioteca antes.")

    resposta = servico.conversar(
        db, "texto",
        [{"role": "system", "content": prompts.buscar(db, "temas_edital_sistema")},
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
