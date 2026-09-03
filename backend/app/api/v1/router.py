from fastapi import APIRouter

from app.api.v1 import ai_admin, auth, estatisticas, health, questoes, simulado

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(questoes.router, tags=["questoes"])
api_router.include_router(ai_admin.router, tags=["ai"])
api_router.include_router(simulado.router, tags=["simulado"])
api_router.include_router(estatisticas.router, tags=["estatisticas"])
