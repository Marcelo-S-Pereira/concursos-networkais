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


class OrcamentoExcedido(SemConexaoIA):
    """Teto diário de gasto em US$ atingido — pausa as chamadas de IA."""


def _checar_orcamento(db: Session) -> None:
    from app.modules.ai_registry.orcamento import diario_excedido

    if diario_excedido(db):
        raise OrcamentoExcedido(
            "Orçamento diário de IA atingido — as chamadas de IA estão pausadas até amanhã (UTC), "
            "para proteger o custo. O admin pode ajustar o teto no painel."
        )


def _com_escolhida(db: Session, cadeia: list, categoria: str, connection_id: int | None) -> list:
    """Põe a conexão escolhida pelo usuário na FRENTE da cadeia.

    O fallback continua atrás: escolher um modelo não deve deixar o aluno na mão
    se aquele modelo cair. Escolha inválida (id inexistente ou de outra
    categoria) é ignorada em silêncio — o padrão da categoria atende.
    """
    if not connection_id:
        return cadeia
    from app.db.models import AiConnection

    escolhida = db.get(AiConnection, connection_id)
    if not escolhida or escolhida.categoria != categoria:
        return cadeia
    return [escolhida, *[c for c in cadeia if c.id != escolhida.id]]


def conversar(db: Session, categoria: str, mensagens: list[dict], *, origem: str,
              max_tokens: int | None = None, user_id: int | None = None,
              connection_id: int | None = None) -> str:
    _checar_orcamento(db)
    cadeia = _com_escolhida(db, cadeia_para_categoria(db, categoria), categoria, connection_id)
    if not cadeia:
        raise SemConexaoIA(f"Nenhuma conexão de IA ativa para a categoria '{categoria}'. Cadastre uma.")

    ultimo_erro: Exception | None = None
    for conn in cadeia:
        inicio = time.monotonic()
        try:
            conteudo, usage = chamar_chat(conn, mensagens, max_tokens=max_tokens)
            registrar(db, connection_id=conn.id, categoria=categoria, origem=origem, modelo=conn.modelo,
                      sucesso=True, latencia_ms=int((time.monotonic() - inicio) * 1000), usage=usage,
                      user_id=user_id)
            return conteudo
        except AiCallError as e:
            registrar(db, connection_id=conn.id, categoria=categoria, origem=origem, modelo=conn.modelo,
                      sucesso=False, latencia_ms=int((time.monotonic() - inicio) * 1000), usage=e.usage,
                      erro=str(e), user_id=user_id)
            ultimo_erro = e  # tenta a próxima da cadeia de fallback, se houver

    raise ultimo_erro or SemConexaoIA(f"Todas as conexões de '{categoria}' falharam.")


def gerar_embeddings(db: Session, textos: list[str], *, origem: str, user_id: int | None = None) -> list[list[float]]:
    _checar_orcamento(db)
    cadeia = cadeia_para_categoria(db, "embeddings")
    if not cadeia:
        raise SemConexaoIA("Nenhuma conexão de IA ativa para 'embeddings'.")
    ultimo_erro: Exception | None = None
    for conn in cadeia:
        inicio = time.monotonic()
        try:
            vetores, usage = chamar_embeddings(conn, textos)
            registrar(db, connection_id=conn.id, categoria="embeddings", origem=origem, modelo=conn.modelo,
                      sucesso=True, latencia_ms=int((time.monotonic() - inicio) * 1000), usage=usage,
                      user_id=user_id)
            return vetores
        except AiCallError as e:
            registrar(db, connection_id=conn.id, categoria="embeddings", origem=origem, modelo=conn.modelo,
                      sucesso=False, latencia_ms=int((time.monotonic() - inicio) * 1000), erro=str(e),
                      user_id=user_id)
            ultimo_erro = e
    raise ultimo_erro or SemConexaoIA("Todas as conexões de 'embeddings' falharam.")
