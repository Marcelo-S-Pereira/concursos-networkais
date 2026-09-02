"""Ponto único que o resto do app chama para falar com IA.

resolve a conexão da categoria → tenta a ativa → em falha, cai para a próxima da
cadeia de fallback (se houver) → registra uso/erro. Custo NÃO é gravado: é
derivado na leitura a partir do preço da conexão.
"""

import time

from sqlalchemy.orm import Session

from app.modules.ai_registry.cliente import AiCallError, chamar_chat, chamar_embeddings
from app.modules.ai_registry.resolver import cadeia_para_categoria
from app.modules.ai_registry.uso import registrar


class SemConexaoIA(Exception):
    pass


def conversar(db: Session, categoria: str, mensagens: list[dict], *, origem: str, max_tokens: int | None = None) -> str:
    cadeia = cadeia_para_categoria(db, categoria)
    if not cadeia:
        raise SemConexaoIA(f"Nenhuma conexão de IA ativa para a categoria '{categoria}'. Cadastre uma.")

    ultimo_erro: Exception | None = None
    for conn in cadeia:
        inicio = time.monotonic()
        try:
            conteudo, usage = chamar_chat(conn, mensagens, max_tokens=max_tokens)
            registrar(db, connection_id=conn.id, categoria=categoria, origem=origem, modelo=conn.modelo,
                      sucesso=True, latencia_ms=int((time.monotonic() - inicio) * 1000), usage=usage)
            return conteudo
        except AiCallError as e:
            registrar(db, connection_id=conn.id, categoria=categoria, origem=origem, modelo=conn.modelo,
                      sucesso=False, latencia_ms=int((time.monotonic() - inicio) * 1000), usage=e.usage, erro=str(e))
            ultimo_erro = e  # tenta a próxima da cadeia de fallback, se houver

    raise ultimo_erro or SemConexaoIA(f"Todas as conexões de '{categoria}' falharam.")


def gerar_embeddings(db: Session, textos: list[str], *, origem: str) -> list[list[float]]:
    cadeia = cadeia_para_categoria(db, "embeddings")
    if not cadeia:
        raise SemConexaoIA("Nenhuma conexão de IA ativa para 'embeddings'.")
    ultimo_erro: Exception | None = None
    for conn in cadeia:
        inicio = time.monotonic()
        try:
            vetores, usage = chamar_embeddings(conn, textos)
            registrar(db, connection_id=conn.id, categoria="embeddings", origem=origem, modelo=conn.modelo,
                      sucesso=True, latencia_ms=int((time.monotonic() - inicio) * 1000), usage=usage)
            return vetores
        except AiCallError as e:
            registrar(db, connection_id=conn.id, categoria="embeddings", origem=origem, modelo=conn.modelo,
                      sucesso=False, latencia_ms=int((time.monotonic() - inicio) * 1000), erro=str(e))
            ultimo_erro = e
    raise ultimo_erro or SemConexaoIA("Todas as conexões de 'embeddings' falharam.")
