"""Point de contrôle de santé de l'application."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

router = APIRouter(tags=["Système"])


@router.get(
    "/health",
    summary="État de l'application et de la base de données",
    description=(
        "Retourne l'état de l'API et la disponibilité de la base PostgreSQL. "
        "Utilisé par les scripts de démarrage et de supervision."
    ),
)
def health(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "indisponible"

    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "application": settings.app_name,
        "version": settings.app_version,
        "environnement": settings.app_env,
    }
