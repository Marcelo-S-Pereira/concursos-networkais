"""Biblioteca RAG em PostgreSQL/pgvector.

Chunk de 900 chars com 100 de sobreposição (corta por parágrafo). 1 embedding
por chunk. Busca por distância de cosseno, só entre vetores do modelo que gerou a
consulta. Os vetores saem de `indexador.py` em segundo plano ([171]): o upload
salva o texto e devolve, o documento fica "em análise" até indexar.
"""

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import RagChunk, RagDocument
from app.modules.ai_registry.servico import gerar_embeddings

log = logging.getLogger("concursos.rag")

CHUNK = 900
OVERLAP = 100


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


def recolocar_na_fila(db: Session, doc: RagDocument) -> None:
    """[171]: a indexação roda em segundo plano (`rag/indexador.py`) — o upload não
    espera mais. Aqui o documento só volta ao estado "em análise"; o indexador
    acha sozinho os trechos sem vetor do modelo atual."""
    doc.indexado_em = None
    doc.erro = None
    db.commit()


def _gerar_descricao(db: Session, titulo: str, texto: str) -> str:
    """Rascunho de descrição pra "memória de conhecimento" ([108]) — melhor
    esforço: sem conexão de IA ou qualquer falha, devolve "" (o admin escreve
    à mão depois). Nunca bloqueia a ingestão."""
    from app.modules.ai_registry import servico
    from app.modules.prompts import prompts as prompts_mod

    try:
        amostra = texto[:6000]
        mensagens = [
            {"role": "system", "content": prompts_mod.buscar(db, "rag_descricao_sistema")},
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

    # os vetores saem do indexador em segundo plano; até lá o documento fica "em análise"
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
    vetores, modelo = gerar_embeddings(db, [consulta], origem="rag_busca", tipo="consulta")
    literal = "[" + ",".join(str(x) for x in vetores[0]) + "]"
    sql = """
        SELECT c.conteudo, d.titulo, c.chunk_index,
               c.embedding <=> CAST(:vec AS vector) AS distancia
        FROM rag_chunks c JOIN rag_documents d ON d.id = c.document_id
        WHERE c.embedding IS NOT NULL AND c.embedding_modelo = :modelo
    """
    params: dict = {"vec": literal, "k": k, "modelo": modelo}
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


# [125]: texto em `prompts` (chave "rag_pergunta_sistema"), não mais aqui.


def perguntar(db: Session, pergunta: str, colecao: str | None = "oficial", k: int = 6, uso: str | None = None) -> dict:
    """Responde uma pergunta ANCORADA nos trechos do edital (RAG), com citação.

    O LLM só sintetiza os trechos recuperados; nunca inventa. Se não houver trecho,
    devolve aviso — nunca uma resposta 'de cabeça'. `uso` ([106]): ver `buscar()`."""
    from app.modules.ai_registry import servico
    from app.modules.prompts import prompts as prompts_mod

    trechos = buscar(db, pergunta, colecao=colecao, k=k, uso=uso)
    if not trechos:
        return {"resposta": "Não há documento indexado para consultar ainda.", "trechos": []}

    contexto = "\n\n".join(f"[trecho {t['chunk']}] {t['conteudo']}" for t in trechos)
    mensagens = [
        {"role": "system", "content": prompts_mod.buscar(db, "rag_pergunta_sistema")},
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
