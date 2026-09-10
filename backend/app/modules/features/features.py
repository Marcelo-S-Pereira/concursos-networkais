"""Liberação de recursos restritos por usuário, com cota diária.

Diferente de estatística de custo (admin-only) — um RECURSO aqui é algo que a
comunidade PODE usar, mas só quem o admin autorizou, com um teto de uso por dia
que o admin decide (ex.: 5 buscas de vídeo por pessoa). Sem grant = sem acesso,
exceto o superadmin, que sempre tem — mas o uso dele também conta no total do
pool, porque é cota real do provedor sendo gasta.

Catálogo extensível: adicionar um recurso novo é uma linha em `RECURSOS`, não
uma tabela nova.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import FeatureGrant, ResourceUsageLog, User

RECURSOS: dict[str, dict] = {
    "youtube_videos": {
        "nome": "Vídeos reais no YouTube",
        "unidade": "buscas por dia",
        "custo_unidade_api": 100,  # unidades da cota do Google por busca (search.list) — documentado, não inventado
    },
}

PADRAO_LIMITE_DIARIO = 5


def _inicio_dia() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _grant(db: Session, user_id: int, feature: str) -> FeatureGrant | None:
    return db.execute(
        select(FeatureGrant).where(FeatureGrant.user_id == user_id, FeatureGrant.feature == feature)
    ).scalar_one_or_none()


def tem_acesso(db: Session, user: User, feature: str) -> bool:
    if user.role == "superadmin":
        return True
    return _grant(db, user.id, feature) is not None


def limite_diario(db: Session, user_id: int, feature: str) -> int:
    g = _grant(db, user_id, feature)
    return g.limite_diario if g else 0


def usado_hoje(db: Session, user_id: int, feature: str) -> int:
    return db.scalar(
        select(func.count()).select_from(ResourceUsageLog).where(
            ResourceUsageLog.user_id == user_id, ResourceUsageLog.feature == feature,
            ResourceUsageLog.criado_em >= _inicio_dia(),
        )
    ) or 0


def uso_total_hoje(db: Session, feature: str) -> int:
    """Soma de todo mundo — para o admin acompanhar o pool real do provedor."""
    return db.scalar(
        select(func.count()).select_from(ResourceUsageLog).where(
            ResourceUsageLog.feature == feature, ResourceUsageLog.criado_em >= _inicio_dia(),
        )
    ) or 0


def excedeu_limite(db: Session, user: User, feature: str) -> bool:
    if user.role == "superadmin":
        return False
    lim = limite_diario(db, user.id, feature)
    if lim <= 0:
        return True  # tem grant mas limite zerado = pausado pelo admin
    return usado_hoje(db, user.id, feature) >= lim


def registrar_uso(db: Session, user_id: int, feature: str) -> None:
    """Best-effort — telemetria de cota não pode derrubar a resposta ao usuário."""
    try:
        db.add(ResourceUsageLog(user_id=user_id, feature=feature))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


def conceder(db: Session, user_id: int, feature: str, limite: int, admin_id: int) -> FeatureGrant:
    g = _grant(db, user_id, feature)
    limite = max(1, limite)
    if g:
        g.limite_diario = limite
        g.concedido_por = admin_id
    else:
        g = FeatureGrant(user_id=user_id, feature=feature, limite_diario=limite, concedido_por=admin_id)
        db.add(g)
    db.commit()
    db.refresh(g)
    return g


def revogar(db: Session, user_id: int, feature: str) -> None:
    g = _grant(db, user_id, feature)
    if g:
        db.delete(g)
        db.commit()


def recursos_do_usuario(db: Session, user: User) -> dict[str, dict]:
    """O que este usuário pode ver/usar de cada recurso do catálogo — para o front."""
    saida: dict[str, dict] = {}
    for chave in RECURSOS:
        liberado = tem_acesso(db, user, chave)
        limite = None
        if liberado and user.role != "superadmin":
            limite = limite_diario(db, user.id, chave)
        saida[chave] = {
            "liberado": liberado,
            "limite_diario": limite,
            "usado_hoje": usado_hoje(db, user.id, chave) if liberado else 0,
        }
    return saida


def grants_do_usuario(db: Session, user_id: int) -> list[dict]:
    """Para a tela do admin: o que esta pessoa já tem liberado, com o uso de hoje."""
    saida = []
    for g in db.execute(select(FeatureGrant).where(FeatureGrant.user_id == user_id)).scalars():
        saida.append({
            "feature": g.feature,
            "nome": RECURSOS.get(g.feature, {}).get("nome", g.feature),
            "limite_diario": g.limite_diario,
            "usado_hoje": usado_hoje(db, user_id, g.feature),
        })
    return saida
