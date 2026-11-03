"""Point d'entrée de l'API ODDS ANALYST.

Rappel de responsabilité : cette application est un outil d'analyse statistique.
Elle ne prédit pas l'issue des rencontres et ne garantit aucun résultat.
Aucun pari n'est placé automatiquement.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.db.seed import seed_defaults
from app.db.session import SessionLocal

logger = logging.getLogger("odds_analyst")

AVERTISSEMENT = (
    "Outil d'analyse statistique. Ne prédit pas l'issue des rencontres, "
    "ne garantit aucun résultat et ne place aucun pari."
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Insère les données de référence au démarrage, si la base est prête."""
    try:
        with SessionLocal() as db:
            seed_defaults(db)
    except Exception as exc:
        logger.warning("Initialisation des données de référence ignorée : %s", exc)
    yield


app = FastAPI(
    title=f"{settings.app_name} — API",
    version=settings.app_version,
    description=AVERTISSEMENT,
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(api_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def racine() -> dict[str, str]:
    return {
        "application": settings.app_name,
        "version": settings.app_version,
        "documentation": "/docs",
        "avertissement": AVERTISSEMENT,
    }
