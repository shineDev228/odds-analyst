"""Référentiel des sports."""

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core import deps
from app.models.reference import Sport
from app.schemas.reference import SportRead

router = APIRouter(
    prefix="/sports",
    tags=["Référentiel"],
    dependencies=[Depends(deps.get_auth_context), Depends(deps.verify_csrf)],
)


@router.get("", response_model=list[SportRead], summary="Lister les sports")
def list_sports(db: deps.DbSession) -> list[Sport]:
    return list(db.scalars(select(Sport).order_by(Sport.name)).all())
