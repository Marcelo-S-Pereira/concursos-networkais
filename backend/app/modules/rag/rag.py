"""Biblioteca RAG em PostgreSQL/pgvector.

Chunk de 900 chars com 100 de sobreposição (corta por parágrafo). 1 embedding
por chunk, em lote. Busca por distância de cosseno. Tolerante: se não houver
conexão de embeddings, o texto do chunk é salvo sem vetor e é reindexado depois.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import RagChunk, RagDocument
from app.modules.ai_registry.servico import SemConexaoIA, gerar_embeddings

log = logging.getLogger("concursos.rag")

CHUNK = 900
OVERLAP = 100
LOTE = 64


def dividir(texto: str) -> list[str]:
    paras = [p.strip() for p in texto.split("\n\n") if p.strip()]
    chunks: list[str] = []
    atual = ""
    for p in paras:
        if len(p) > CHUNK:
            if atual:
                chunks.append(atual)
                atual = ""
            passo = CHUNK - OVERLAP
            for i in range(0, len(p), passo):
                chunks.append(p[i : i + CHUNK])
            continue
        if len(atual) + len(p) + 2 > CHUNK:
            chunks.append(atual)
            atual = ""
        atual = f"{atual}\n\n{p}" if atual else p
    if atual:
        chunks.append(atual)
    return chunks


def _embed_pendentes(db: Session, doc: RagDocument) -> None:
    """Gera embeddings para os chunks sem vetor deste documento, em lote.

    [110]: conta a tentativa ANTES de chamar a IA — mesmo que falhe no meio,
    a tentativa aconteceu; é o que "tentativas_indexacao" mostra pro admin."""
    pendentes = db.execute(
        select(RagChunk).where(RagChunk.document_id == doc.id, RagChunk.embedding.is_(None))
    ).scalars().all()
    if not pendentes:
        return
    doc.tentativas_indexacao += 1
    db.commit()
    for i in range(0, len(pendentes), LOTE):
        bloco = pendentes[i : i + LOTE]
        vetores = gerar_embeddings(db, [f"passage: {c.conteudo}" for c in bloco], origem="rag_ingest")
        for chunk, vetor in zip(bloco, vetores, strict=True):
            chunk.embedding = vetor
    db.commit()


def _gerar_descricao(db: Session, titulo: str, texto: str) -> str:
    """Rascunho de descrição pra "memória de conhecimento" ([108]) — melhor
    esforço: sem conexão de IA ou qualquer falha, devolve "" (o admin escreve
    à mão depois). Nunca bloqueia a ingestão."""
    from app.modules.ai_registry import servico

    try:
        amostra = texto[:6000]
        mensagens = [
            {"role": "system", "content": (
                "Resuma em até 2 frases curtas (máx 300 caracteres) do que trata este documento — "
                "assunto, disciplina, tipo de conteúdo. Sem introdução, sem markdown, só o resumo."
            )},
            {"role": "user", "content": f"Título: {titulo}\n\nTrecho do documento:\n{amostra}"},
        ]
        resposta = servico.conversar(db, "texto", mensagens, origem="rag_descricao", max_tokens=150)
        return resposta.strip()[:500]
    except Exception:  # noqa: BLE001 — best-effort; falha aqui não pode travar o import
        return ""


def ingerir_documento(
    db: Session, titulo: str, texto: str, colecao: str = "oficial", origem: str = "",
    uso_chat: bool = False, uso_tutor: bool = False, uso_simulado: bool = False,
    enviado_por_user_id: int | None = None,
) -> RagDocument:
    descricao = _gerar_descricao(db, titulo, texto)
    doc = RagDocument(titulo=titulo, descricao=descricao, colecao=colecao, origem=origem,
                       uso_chat=uso_chat, uso_tutor=uso_tutor, uso_simulado=uso_simulado,
                       enviado_por_user_id=enviado_por_user_id)
    db.add(doc)
    db.flush()
    pedacos = dividir(texto)
    for i, c in enumerate(pedacos):
        db.add(RagChunk(document_id=doc.id, colecao=colecao, chunk_index=i, conteudo=c))
    doc.chunk_count = len(pedacos)
    db.commit()

    # tenta indexar já; se não houver conexão de embeddings, fica pendente
    try:
        _embed_pendentes(db, doc)
        doc.indexado_em = datetime.now(UTC)
        doc.erro = None
    except SemConexaoIA:
        doc.erro = "sem conexão de embeddings — chunks salvos, reindexar depois"
    except Exception as e:  # noqa: BLE001
        doc.erro = str(e)[:500]
    db.commit()
    db.refresh(doc)
    return doc


# [106]: allowlist fixa — nunca interpolar o parâmetro `uso` (vindo de chamador)
# direto num nome de coluna SQL. Cada ferramenta futura passa sua própria chave.
COLUNA_USO = {"chat": "uso_chat", "tutor": "uso_tutor", "simulado": "uso_simulado"}


def buscar(
    db: Session, consulta: str, colecao: str | None = None, k: int = 6, uso: str | None = None,
    doc_ids: list[int] | None = None,
) -> list[dict]:
    """Busca por similaridade de cosseno. Só entre chunks já vetorizados.

    `uso` ([106]) filtra pela classificação do documento ("chat"/"tutor"/
    "simulado") — None (o padrão, usado pelas ferramentas de gestão da
    biblioteca, "Perguntar ao edital"/"Buscar trechos") busca em tudo.
    `doc_ids` ([110]): quando a conversa do Tutor tem seleção própria de
    documentos, restringe a busca só a eles (dentro do `uso` já filtrado)."""
    vetor = gerar_embeddings(db, [f"Instruct: buscar trecho relevante\nQuery: {consulta}"], origem="rag_busca")[0]
    literal = "[" + ",".join(str(x) for x in vetor) + "]"
    sql = """
        SELECT c.conteudo, d.titulo, c.chunk_index,
               c.embedding <=> CAST(:vec AS vector) AS distancia
        FROM rag_chunks c JOIN rag_documents d ON d.id = c.document_id
        WHERE c.embedding IS NOT NULL
    """
    params: dict = {"vec": literal, "k": k}
    if colecao:
        sql += " AND c.colecao = :colecao"
        params["colecao"] = colecao
    if uso:
        coluna = COLUNA_USO.get(uso)
        if not coluna:
            raise ValueError(f"uso inválido: {uso!r} — use um de {sorted(COLUNA_USO)}")
        sql += f" AND d.{coluna} = true"  # noqa: S608 — coluna vem só da allowlist acima, não do chamador
    if doc_ids:
        sql += " AND d.id = ANY(:doc_ids)"
        params["doc_ids"] = doc_ids
    sql += " ORDER BY c.embedding <=> CAST(:vec AS vector) LIMIT :k"
    linhas = db.execute(text(sql), params).all()
    return [{"titulo": t, "chunk": idx, "conteudo": cont, "distancia": float(dist)}
            for cont, t, idx, dist in linhas]


PERGUNTA_SISTEMA = (
    "Você responde dúvidas sobre um EDITAL de concurso APENAS com base nos trechos "
    "fornecidos abaixo. Se a resposta não estiver nos trechos, diga claramente que o "
    "edital, nos trechos encontrados, não trata disso — NUNCA invente regra, prazo, "
    "número de vagas, data ou critério. Cite o número do trecho que embasa cada afirmação. "
    "Seja objetivo e direto."
)


def perguntar(db: Session, pergunta: str, colecao: str | None = "oficial", k: int = 6, uso: str | None = None) -> dict:
    """Responde uma pergunta ANCORADA nos trechos do edital (RAG), com citação.

    O LLM só sintetiza os trechos recuperados; nunca inventa. Se não houver trecho,
    devolve aviso — nunca uma resposta 'de cabeça'. `uso` ([106]): ver `buscar()`."""
    from app.modules.ai_registry import servico

    trechos = buscar(db, pergunta, colecao=colecao, k=k, uso=uso)
    if not trechos:
        return {"resposta": "Não há documento indexado para consultar ainda.", "trechos": []}

    contexto = "\n\n".join(f"[trecho {t['chunk']}] {t['conteudo']}" for t in trechos)
    mensagens = [
        {"role": "system", "content": PERGUNTA_SISTEMA},
        {"role": "user", "content": f"Pergunta: {pergunta}\n\nTrechos do edital:\n{contexto}"},
    ]
    resposta = servico.conversar(db, "texto", mensagens, origem="rag_pergunta", max_tokens=800)
    return {"resposta": (resposta or "").strip(), "trechos": trechos}


def contexto_biblioteca(db: Session, consulta: str, uso: str, k: int = 4, doc_ids: list[int] | None = None) -> str:
    """[108]: motor de recuperação compartilhado — Chat de estudos e Tutor IA
    ([109]) chamam isto pra montar um bloco de contexto pronto pra injetar
    no prompt, só com os documentos classificados pra aquele `uso` ([106]).
    `doc_ids` ([110]): quando o usuário escolheu documentos específicos pra
    aquela conversa do Tutor, restringe a busca a eles.

    Best-effort de propósito: sem documento classificado, sem conexão de
    embeddings, ou qualquer falha — devolve "" e NUNCA lança. Uma resposta
    do chat não pode quebrar por causa de um recurso de apoio opcional."""
    try:
        trechos = buscar(db, consulta, k=k, uso=uso, doc_ids=doc_ids)
    except Exception:  # noqa: BLE001 — apoio opcional; nunca derruba a resposta principal
        return ""
    if not trechos:
        return ""
    corpo = "\n\n".join(f"[{t['titulo']} — trecho {t['chunk']}] {t['conteudo']}" for t in trechos)
    return (
        "Trechos de referência da biblioteca do usuário (documentos que ele mesmo escolheu pra "
        "este uso). Use e cite só se realmente ajudarem a responder a pergunta atual; se não "
        "ajudarem, ignore completamente e responda normalmente, sem mencionar isto:\n\n" + corpo
    )
