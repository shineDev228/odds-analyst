"""Point d'entrée de l'API ODDS ANALYST.

Rappel de responsabilité : cette application est un outil d'analyse statistique.
Elle ne prédit pas l'issue des rencontres et ne garantit aucun résultat.
Aucun pari n'est placé automatiquement.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings

AVERTISSEMENT = (
    "Outil d'analyse statistique. Ne prédit pas l'issue des rencontres, "
    "ne garantit aucun résultat et ne place aucun pari."
)

app = FastAPI(
    title=f"{settings.app_name} — API",
    version=settings.app_version,
    description=AVERTISSEMENT,
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def racine() -> dict[str, str]:
    return {
        "application": settings.app_name,
        "version": settings.app_version,
        "documentation": "/docs",
        "avertissement": AVERTISSEMENT,
    }
