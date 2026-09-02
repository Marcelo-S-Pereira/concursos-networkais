from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db


def usuario_atual(request: Request, db: Session = Depends(get_db)) -> User:
    """Exige sessão válida. Use como dependência em toda rota que não seja pública."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Não autenticado.")
    user = db.get(User, user_id)
    if not user:
        # Sessão aponta para usuário que não existe mais - derruba a sessão.
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Não autenticado.")
    return user
