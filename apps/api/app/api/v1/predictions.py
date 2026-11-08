"""Analyse statistique des rencontres."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core import deps
from app.schemas.prediction import PredictionRead
from app.services.predictions import InsufficientHistoryError, build_prediction

router = APIRouter(
    tags=["Analyse statistique"],
    dependencies=[Depends(deps.get_auth_context), Depends(deps.verify_csrf)],
)


@router.get(
    "/matches/{match_id}/prediction",
    response_model=PredictionRead,
    summary="Analyse statistique d'une rencontre",
)
def get_prediction(match_id: UUID, db: deps.DbSession) -> PredictionRead:
    try:
        return build_prediction(db, match_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InsufficientHistoryError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
