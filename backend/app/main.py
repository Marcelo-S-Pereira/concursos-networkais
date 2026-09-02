from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="APP Concursos", version="0.1.0", docs_url=None if settings.is_production else "/docs")

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
