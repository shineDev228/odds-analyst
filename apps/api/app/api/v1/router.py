"""Routeur principal de l'API v1."""

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    competitions,
    dashboard,
    health,
    markets,
    matches,
    predictions,
    seasons,
    settings,
    sports,
    teams,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(sports.router)
api_router.include_router(competitions.router)
api_router.include_router(seasons.router)
api_router.include_router(teams.router)
api_router.include_router(matches.router)
api_router.include_router(markets.router)
api_router.include_router(predictions.router)
api_router.include_router(dashboard.router)
api_router.include_router(settings.router)
