"""Générateur de combinaisons de sélections."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core import deps
from app.schemas.combination import CombinationRequest, CombinationResponse
from app.services.combinations import InvalidCombinationRequest, build_combinations

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
