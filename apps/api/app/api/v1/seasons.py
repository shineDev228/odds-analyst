"""Saisons."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.api.v1._helpers import commit_or_conflict, conflict, not_found
from app.core import deps
from app.models.match import Match
from app.models.reference import Competition, Season
from app.schemas.common import Page
from app.schemas.reference import SeasonCreate, SeasonRead, SeasonUpdate
from app.services import audit

router = APIRouter(
    prefix="/seasons",
    tags=["Saisons"],
    dependencies=[Depends(deps.get_auth_context), Depends(deps.verify_csrf)],
)


@router.get("", response_model=Page[SeasonRead], summary="Lister les saisons")
def list_seasons(
    db: deps.DbSession,
    competition_id: UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[SeasonRead]:
    conditions: list[ColumnElement[bool]] = []
    if competition_id:
        conditions.append(Season.competition_id == competition_id)

    total = db.scalar(select(func.count()).select_from(Season).where(*conditions)) or 0
    items = db.scalars(
        select(Season)
        .where(*conditions)
        .order_by(Season.label.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(
        items=[SeasonRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=SeasonRead,
    status_code=status.HTTP_201_CREATED,
    summary="Créer une saison",
)
def create_season(
    payload: SeasonCreate, db: deps.DbSession, user: deps.CurrentUser
) -> Season:
    if db.get(Competition, payload.competition_id) is None:
        not_found("Compétition introuvable.")

    season = Season(**payload.model_dump())
    db.add(season)
    commit_or_conflict(db, "Cette saison existe déjà pour cette compétition.")
    db.refresh(season)
    audit.record(db, "season.create", user_id=user.id, entity="season",
                 entity_id=str(season.id), payload=payload.model_dump(mode="json"))
    return season


def _get(db: Session, season_id: UUID) -> Season:
    season = db.get(Season, season_id)
    if season is None:
        not_found("Saison introuvable.")
    return season


@router.patch("/{season_id}", response_model=SeasonRead, summary="Modifier une saison")
def update_season(
    season_id: UUID, payload: SeasonUpdate, db: deps.DbSession, user: deps.CurrentUser
) -> Season:
    season = _get(db, season_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(season, field, value)
    commit_or_conflict(db, "Cette saison existe déjà pour cette compétition.")
    db.refresh(season)
    audit.record(
        db,
        "season.update",
        user_id=user.id,
        entity="season",
        entity_id=str(season.id),
        payload=payload.model_dump(exclude_unset=True, mode="json"),
    )
    return season


@router.delete(
    "/{season_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Supprimer une saison"
)
def delete_season(season_id: UUID, db: deps.DbSession, user: deps.CurrentUser) -> None:
    season = _get(db, season_id)
    has_matches = db.scalar(
        select(func.count()).select_from(Match).where(Match.season_id == season_id)
    )
    if has_matches:
        conflict("Impossible de supprimer : des rencontres sont rattachées à cette saison.")
    db.delete(season)
    db.commit()
    audit.record(db, "season.delete", user_id=user.id, entity="season", entity_id=str(season_id))
