"""Log de uso de IA. NUNCA lança — telemetria não pode derrubar a resposta.

[170] Cada linha diz QUEM (user_id), EM QUAL FERRAMENTA (ferramenta) e EM QUAL
AÇÃO do usuário (acao_id) a chamada aconteceu. Isso vem de um contexto por
requisição, não de parâmetros passados por dezenas de chamadas:

- `UsoContextoMiddleware` (ASGI, dentro do SessionMiddleware) abre o contexto
  com o usuário da sessão e um `acao_id` novo por requisição;
- a rota completa com `marcar(ferramenta=..., conversation_id=...)`;
- `registrar()` lê dali. Qualquer chamada de IA feita durante a requisição —
  inclusive a busca na biblioteca que o chat faz por baixo — fica atribuída à
  pessoa e à ferramenta certas, sem ninguém precisar lembrar de repassar.

Por que `acao_id`: uma mensagem de voz gera 4 linhas (transcrição, busca,
LLM, voz). Contar chamadas puniria a pessoa por como o sistema é montado; a
unidade justa para limite é a AÇÃO.
"""

import logging
import uuid
from contextvars import ContextVar

from sqlalchemy.orm import Session

from app.db.models import AiCallLog

log = logging.getLogger("concursos.ai")

FERRAMENTAS = (
    "chat_estudo", "tutor_ia", "tutor_ia_tempo_real", "simulado_tutor",
    "gemeas", "passo_a_passo", "admin",
)

# Quando a rota não marcou a ferramenta, a origem da chamada decide. As origens
# `chat_*` ficam de fora de propósito: Chat de estudo e Tutor IA usam as mesmas,
# só a rota (a conversa) sabe qual dos dois é — se chegar sem marca, fica NULL
# e aparece no painel como "sem ferramenta", em vez de chutar.
_POR_ORIGEM = {
    "tutor_explica": "simulado_tutor",
    "gemeas": "gemeas",
    "tutor_passo_a_passo": "passo_a_passo",
    "tutor_passo_a_passo_tts": "passo_a_passo",
}
_PREFIXOS_ADMIN = ("rag_", "extrair_subtemas", "transcricao", "afericao", "teste", "diag")


def ferramenta_da_origem(origem: str) -> str | None:
    if origem in _POR_ORIGEM:
        return _POR_ORIGEM[origem]
    if origem.startswith(_PREFIXOS_ADMIN):
        return "admin"
    return None


_CTX: ContextVar[dict | None] = ContextVar("uso_contexto", default=None)


def contexto_atual() -> dict:
    return dict(_CTX.get() or {})


def marcar(**campos) -> None:
    """Completa o contexto da requisição (ferramenta, conversation_id, user_id,
    acao_id). Valores None não apagam o que já estava."""
    atual = contexto_atual()
    atual.update({k: v for k, v in campos.items() if v is not None})
    _CTX.set(atual)


def nova_acao() -> str:
    """Abre uma ação nova dentro do mesmo contexto (ex.: cada turno de uma
    conversa por voz, que vive numa conexão só)."""
    acao = uuid.uuid4().hex
    marcar(acao_id=acao)
    return acao


class UsoContextoMiddleware:
    """ASGI puro (sem BaseHTTPMiddleware): abre o contexto de uso de cada
    requisição HTTP/WebSocket. Precisa ficar DENTRO do SessionMiddleware, que é
    quem popula `scope["session"]`."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        sessao = scope.get("session") or {}
        token = _CTX.set({"user_id": sessao.get("user_id"), "acao_id": uuid.uuid4().hex})
        try:
            await self.app(scope, receive, send)
        finally:
            _CTX.reset(token)


def registrar(
    db: Session,
    *,
    connection_id: int | None,
    categoria: str,
    origem: str,
    modelo: str,
    sucesso: bool,
    latencia_ms: int,
    usage: dict | None = None,
    unidades: int | None = None,
    tipo_unidade: str | None = None,
    erro: str | None = None,
    user_id: int | None = None,
    ferramenta: str | None = None,
    conversation_id: int | None = None,
    acao_id: str | None = None,
) -> None:
    try:
        usage = usage or {}
        ctx = _CTX.get() or {}
        db.add(
            AiCallLog(
                connection_id=connection_id,
                user_id=user_id if user_id is not None else ctx.get("user_id"),
                categoria=categoria,
                origem=origem,
                modelo=modelo,
                sucesso=sucesso,
                latencia_ms=latencia_ms,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                unidades=unidades,
                tipo_unidade=tipo_unidade,
                erro=(erro or "")[:500] or None,
                ferramenta=ferramenta or ctx.get("ferramenta") or ferramenta_da_origem(origem),
                conversation_id=conversation_id if conversation_id is not None else ctx.get("conversation_id"),
                acao_id=acao_id or ctx.get("acao_id"),
            )
        )
        db.commit()
    except Exception as e:  # noqa: BLE001 - telemetria é best-effort
        db.rollback()
        log.error("falha ao gravar ai_call_log (resposta ao usuário não afetada): %s", e)
