"""Ponto único que o resto do app chama para falar com IA.

resolve a conexão da categoria → tenta a ativa → em falha, cai para a próxima da
cadeia de fallback (se houver) → registra uso/erro. Custo NÃO é gravado: é
derivado na leitura a partir do preço da conexão.
"""

import time

from sqlalchemy.orm import Session

from app.modules.ai_registry import cliente, fila
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

    with fila.vaga(db):
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


# Voz padrão por modelo, quando o chamador não escolhe uma — chave em minúsculo
# do model id. Kokoro tem português do Brasil (pf_dora, feminina); os demais
# entram conforme forem cadastrados.
VOZES_PADRAO = {
    "hexgrad/kokoro-82m": "pf_dora",
}


def transcrever_audio(db: Session, audio_bytes: bytes, nome_arquivo: str, *, origem: str,
                       user_id: int | None = None, connection_id: int | None = None,
                       idioma: str = "pt") -> dict:
    """STT. Retorna {"texto": str, "duracao_s": float}."""
    _checar_orcamento(db)
    cadeia = _com_escolhida(db, cadeia_para_categoria(db, "transcricao"), "transcricao", connection_id)
    if not cadeia:
        raise SemConexaoIA("Nenhuma conexão de IA ativa para 'transcricao'. Cadastre uma.")

    with fila.vaga(db):
        ultimo_erro: Exception | None = None
        for conn in cadeia:
            inicio = time.monotonic()
            try:
                resultado = cliente.transcrever(conn, audio_bytes, nome_arquivo, idioma=idioma)
                registrar(db, connection_id=conn.id, categoria="transcricao", origem=origem, modelo=conn.modelo,
                          sucesso=True, latencia_ms=int((time.monotonic() - inicio) * 1000),
                          unidades=int(resultado["duracao_s"]) or None, tipo_unidade="segundos", user_id=user_id)
                return resultado
            except AiCallError as e:
                registrar(db, connection_id=conn.id, categoria="transcricao", origem=origem, modelo=conn.modelo,
                          sucesso=False, latencia_ms=int((time.monotonic() - inicio) * 1000), erro=str(e),
                          user_id=user_id)
                ultimo_erro = e

        raise ultimo_erro or SemConexaoIA("Todas as conexões de 'transcricao' falharam.")


def falar_texto(db: Session, texto: str, *, origem: str, user_id: int | None = None,
                connection_id: int | None = None, voz: str | None = None) -> bytes:
    """TTS. Retorna os bytes do áudio (mp3)."""
    _checar_orcamento(db)
    cadeia = _com_escolhida(db, cadeia_para_categoria(db, "voz"), "voz", connection_id)
    if not cadeia:
        raise SemConexaoIA("Nenhuma conexão de IA ativa para 'voz'. Cadastre uma.")

    with fila.vaga(db):
        ultimo_erro: Exception | None = None
        for conn in cadeia:
            v = voz or VOZES_PADRAO.get((conn.modelo or "").lower(), "alloy")
            inicio = time.monotonic()
            try:
                audio = cliente.falar(conn, texto, v)
                registrar(db, connection_id=conn.id, categoria="voz", origem=origem, modelo=conn.modelo,
                          sucesso=True, latencia_ms=int((time.monotonic() - inicio) * 1000),
                          unidades=len(texto), tipo_unidade="caracteres", user_id=user_id)
                return audio
            except AiCallError as e:
                registrar(db, connection_id=conn.id, categoria="voz", origem=origem, modelo=conn.modelo,
                          sucesso=False, latencia_ms=int((time.monotonic() - inicio) * 1000), erro=str(e),
                          user_id=user_id)
                ultimo_erro = e

        raise ultimo_erro or SemConexaoIA("Todas as conexões de 'voz' falharam.")


def prefixar_embedding(modelo: str, tipo: str, texto: str) -> str:
    """[171]: cada família de modelo espera um formato de entrada próprio; usar o
    errado não dá erro, só piora a busca em silêncio. `tipo`: passagem | consulta."""
    m = modelo.lower()
    if "e5" not in m:
        return texto
    if tipo == "passagem":
        return f"passage: {texto}"
    return f"Instruct: buscar trecho relevante\nQuery: {texto}" if "instruct" in m else f"query: {texto}"


def modelo_de_embeddings(db: Session) -> str | None:
    """Modelo que a conexão ativa de embeddings usa hoje (é o que carimba os vetores)."""
    cadeia = cadeia_para_categoria(db, "embeddings")
    return cadeia[0].modelo if cadeia else None


def gerar_embeddings(
    db: Session, textos: list[str], *, origem: str, user_id: int | None = None,
    tipo: str = "passagem", somente_primeira: bool = False,
) -> tuple[list[list[float]], str]:
    """Devolve (vetores, modelo que os gerou). Vetores de modelos diferentes não
    se comparam, então quem guarda ou busca precisa saber de qual modelo vieram.
    `somente_primeira` desliga o fallback — indexação em massa não pode misturar."""
    cadeia = cadeia_para_categoria(db, "embeddings")
    if not cadeia:
        raise SemConexaoIA("Nenhuma conexão de IA ativa para 'embeddings'.")
    if somente_primeira:
        cadeia = cadeia[:1]
    with fila.vaga(db):
        ultimo_erro: Exception | None = None
        for conn in cadeia:
            if not conn.endpoint.startswith("local://"):
                _checar_orcamento(db)
            inicio = time.monotonic()
            try:
                vetores, usage = chamar_embeddings(conn, [prefixar_embedding(conn.modelo, tipo, t) for t in textos])
                registrar(db, connection_id=conn.id, categoria="embeddings", origem=origem, modelo=conn.modelo,
                          sucesso=True, latencia_ms=int((time.monotonic() - inicio) * 1000), usage=usage,
                          user_id=user_id)
                return vetores, conn.modelo
            except AiCallError as e:
                registrar(db, connection_id=conn.id, categoria="embeddings", origem=origem, modelo=conn.modelo,
                          sucesso=False, latencia_ms=int((time.monotonic() - inicio) * 1000), erro=str(e),
                          user_id=user_id)
                ultimo_erro = e
        raise ultimo_erro or SemConexaoIA("Todas as conexões de 'embeddings' falharam.")
