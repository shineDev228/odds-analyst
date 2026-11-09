"""Analyse statistique des rencontres."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core import deps
from app.schemas.calibration import CalibrationRead
from app.schemas.prediction import PredictionRead
from app.services.calibration import DEFAULT_LIMIT, MAX_LIMIT, MIN_LIMIT, build_calibration
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


@router.get(
    "/predictions/calibration",
    response_model=CalibrationRead,
    summary="Rétro-test de calibration du modèle",
)
def get_calibration(
    db: deps.DbSession,
    limit: Annotated[int, Query(ge=MIN_LIMIT, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> CalibrationRead:
    """Compare les prévisions passées aux résultats réels, sans fuite de données."""
    return build_calibration(db, limit=limit)
