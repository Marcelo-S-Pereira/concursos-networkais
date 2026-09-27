import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.router import api_router
from app.api.ws_voz import router as ws_voz_router
from app.core.config import get_settings
from app.core.monitor import loop_monitor
from app.modules.ai_registry.fila import FilaEsgotada
from app.modules.ai_registry.uso import UsoContextoMiddleware

settings = get_settings()


def _aquecer_embeddings() -> None:
    """[171]: carrega o modelo local de embeddings ao subir. Sem isso, a 1ª busca
    depois de cada reinício paga ~3 s de carga dentro de uma mensagem de chat."""
    try:
        from app.db.session import SessionLocal
        from app.modules.ai_registry import embeddings_locais
        from app.modules.ai_registry.resolver import cadeia_para_categoria

        with SessionLocal() as db:
            cadeia = cadeia_para_categoria(db, "embeddings")
            local = cadeia[0].modelo if cadeia and cadeia[0].endpoint.startswith("local://") else None
        if local:
            embeddings_locais.carregar(local)
    except Exception:  # noqa: BLE001 — aquecer é conforto, nunca pode impedir a API de subir
        logging.getLogger("concursos").exception("não consegui aquecer o modelo de embeddings")


@asynccontextmanager
async def lifespan(_: FastAPI):
    tarefa = asyncio.create_task(loop_monitor())  # vigia a saúde da ambiente de execucao em segundo plano
    aquecer = asyncio.create_task(asyncio.to_thread(_aquecer_embeddings))
    try:
        yield
    finally:
        tarefa.cancel()
        aquecer.cancel()


app = FastAPI(
    title="APP Concursos", version="0.1.0",
    docs_url=None if settings.is_production else "/docs", lifespan=lifespan,
)

# [170] Contexto de uso de IA (quem, qual ação). O último middleware adicionado é
# o mais externo — este entra ANTES do SessionMiddleware para ficar dentro dele e
# poder ler `scope["session"]`.
app.add_middleware(UsoContextoMiddleware)

# Sessão em cookie assinado. HttpOnly (JavaScript não lê), SameSite=lax (corta
# CSRF de navegação cruzada) e Secure em produção, onde tudo é HTTPS.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie="concursos_sessao",
    same_site="lax",
    https_only=True,
    max_age=60 * 60 * 24 * 14,  # 14 dias
)

# CORS não é necessário: em dev o Vite faz proxy e em produção o nginx serve o
# front na MESMA origem da API. Sem CORS liberado, o cookie de sessão não pode
# ser usado por outro site.

app.include_router(api_router)
# [135]: fora do prefixo /api/v1 de propósito — casa com a reserva
# `location /ws/` que já existe no nginx desde o [011] (upgrade de conexão).
app.include_router(ws_voz_router)


# [126]: fila de admissão para chamadas de IA — qualquer rota que acabe
# esgotando o tempo de espera vira 503 aqui, sem precisar de `except` em
# cada uma das dezenas de rotas que chamam IA (chat/questoes/tutor...).
@app.exception_handler(FilaEsgotada)
async def _fila_esgotada_handler(_: Request, exc: FilaEsgotada) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})
