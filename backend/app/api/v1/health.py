from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()


@router.get("/health")
def health(request: Request, db: Session = Depends(get_db)) -> dict:
    """Prova que a API está de pé E que o banco responde de verdade.

    Health que devolve 200 sem tocar no banco mente exatamente quando mais
    importa - quando o banco caiu e a API continua respondendo.

    A rota é pública (monitoramento precisa dela), mas **versão de componente só
    aparece para quem está autenticado**: número de versão é reconhecimento de
    alvo para quem procura vulnerabilidade conhecida.
    """
    db_ok = False
    vector_version: str | None = None
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
        vector_version = db.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
    except SQLAlchemyError:
        # Health nunca propaga erro: ele RELATA o estado. Se o banco caiu, a
        # resposta tem que dizer "degraded", não devolver 500.
        db_ok = False

    corpo: dict = {"status": "ok" if db_ok else "degraded"}
    if request.session.get("user_id"):
        corpo["database"] = db_ok
        corpo["pgvector"] = vector_version
    return corpo
