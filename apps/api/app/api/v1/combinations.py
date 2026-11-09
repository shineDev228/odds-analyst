"""Générateur et historique des combinaisons de sélections."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1._helpers import not_found
from app.core import deps
from app.schemas.combination import CombinationRequest, CombinationResponse
from app.schemas.common import Page
from app.schemas.history import (
    CombinationSaveRequest,
    PerformanceSummaryRead,
    SavedCombinationRead,
)
from app.services.combinations import InvalidCombinationRequest, build_combinations
from app.services.history import (
    HistoryNotFound,
    InvalidSave,
    build_performance,
    delete_combination,
    get_combination,
    list_combinations,
)
from app.services.history import save_combination as save_combination_service

router = APIRouter(
    prefix="/combinations",
    tags=["Combinaisons"],
    dependencies=[Depends(deps.get_auth_context), Depends(deps.verify_csrf)],
)


@router.post(
    "/generate",
    response_model=CombinationResponse,
    summary="Générer des combinaisons de sélections",
)
def generate_combinations(
    payload: CombinationRequest,
    db: deps.DbSession,
) -> CombinationResponse:
    """Calcule à la demande des combinaisons dont la cote totale est bornée."""
    try:
        return build_combinations(db, payload)
    except InvalidCombinationRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post(
    "",
    response_model=SavedCombinationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Enregistrer une combinaison",
)
def save_combination(
    payload: CombinationSaveRequest,
    db: deps.DbSession,
    user: deps.CurrentUser,
) -> SavedCombinationRead:
    """Valide la combinaison côté serveur puis la conserve avec ses cotes."""
    try:
        return save_combination_service(db, user, payload)
    except InvalidSave as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/performance",
    response_model=PerformanceSummaryRead,
    summary="Synthèse de performance de l'historique",
)
def performance(db: deps.DbSession, user: deps.CurrentUser) -> PerformanceSummaryRead:
    return build_performance(db, user)


@router.get(
    "",
    response_model=Page[SavedCombinationRead],
    summary="Lister les combinaisons enregistrées",
)
def list_saved_combinations(
    db: deps.DbSession,
    user: deps.CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    statut: Annotated[
        str,
        Query(pattern="^(toutes|en_attente|gagnee|perdue|remboursee|indisponible)$"),
    ] = "toutes",
) -> Page[SavedCombinationRead]:
    return list_combinations(
        db,
        user,
        page=page,
        page_size=page_size,
        status=statut,
    )


@router.get(
    "/{combination_id}",
    response_model=SavedCombinationRead,
    summary="Détail d'une combinaison enregistrée",
)
def read_saved_combination(
    combination_id: UUID,
    db: deps.DbSession,
    user: deps.CurrentUser,
) -> SavedCombinationRead:
    try:
        return get_combination(db, user, combination_id)
    except HistoryNotFound as exc:
        not_found(str(exc))


@router.delete(
    "/{combination_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer une combinaison enregistrée",
)
def remove_saved_combination(
    combination_id: UUID,
    db: deps.DbSession,
    user: deps.CurrentUser,
) -> None:
    try:
        delete_combination(db, user, combination_id)
    except HistoryNotFound as exc:
        not_found(str(exc))
