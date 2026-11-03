"""Compétitions."""

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
from app.schemas.reference import CompetitionCreate, CompetitionRead, CompetitionUpdate
from app.services import audit

router = APIRouter(
    prefix="/competitions",
    tags=["Compétitions"],
    dependencies=[Depends(deps.get_auth_context), Depends(deps.verify_csrf)],
)


@router.get("", response_model=Page[CompetitionRead], summary="Lister les compétitions")
def list_competitions(
    db: deps.DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    search: Annotated[str | None, Query(max_length=120)] = None,
    sport_id: UUID | None = None,
) -> Page[CompetitionRead]:
    conditions: list[ColumnElement[bool]] = []
    if search:
        conditions.append(Competition.name.ilike(f"%{search}%"))
    if sport_id:
        conditions.append(Competition.sport_id == sport_id)

    total = db.scalar(select(func.count()).select_from(Competition).where(*conditions)) or 0
    items = db.scalars(
        select(Competition)
        .where(*conditions)
        .order_by(Competition.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(
        items=[CompetitionRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=CompetitionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Créer une compétition",
)
def create_competition(
    payload: CompetitionCreate,
    db: deps.DbSession,
    user: deps.CurrentUser,
) -> Competition:
    existing = db.scalar(
        select(Competition).where(
            Competition.sport_id == payload.sport_id,
            Competition.name == payload.name,
            Competition.country.is_(None)
            if payload.country is None
            else Competition.country == payload.country,
        )
    )
    if existing is not None:
        commit_or_conflict(db, "Cette compétition existe déjà pour ce sport et ce pays.")

    competition = Competition(**payload.model_dump())
    db.add(competition)
    commit_or_conflict(db, "Cette compétition existe déjà pour ce sport et ce pays.")
    db.refresh(competition)
    audit.record(db, "competition.create", user_id=user.id, entity="competition",
                 entity_id=str(competition.id), payload=payload.model_dump(mode="json"))
    return competition


def _get(db: Session, competition_id: UUID) -> Competition:
    competition = db.get(Competition, competition_id)
    if competition is None:
        not_found("Compétition introuvable.")
    return competition


@router.get("/{competition_id}", response_model=CompetitionRead, summary="Détail d'une compétition")
def get_competition(competition_id: UUID, db: deps.DbSession) -> Competition:
    return _get(db, competition_id)


@router.patch(
    "/{competition_id}",
    response_model=CompetitionRead,
    summary="Modifier une compétition",
)
def update_competition(
    competition_id: UUID,
    payload: CompetitionUpdate,
    db: deps.DbSession,
    user: deps.CurrentUser,
) -> Competition:
    competition = _get(db, competition_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(competition, field, value)
    commit_or_conflict(db, "Une compétition portant ce nom existe déjà.")
    db.refresh(competition)
    audit.record(
        db,
        "competition.update",
        user_id=user.id,
        entity="competition",
        entity_id=str(competition.id),
        payload=payload.model_dump(exclude_unset=True, mode="json"),
    )
    return competition


@router.delete(
    "/{competition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer une compétition",
)
def delete_competition(
    competition_id: UUID, db: deps.DbSession, user: deps.CurrentUser
) -> None:
    competition = _get(db, competition_id)
    has_matches = db.scalar(
        select(func.count())
        .select_from(Match)
        .join(Season, Season.id == Match.season_id)
        .where(Season.competition_id == competition_id)
    )
    if has_matches:
        conflict("Impossible de supprimer : des rencontres sont rattachées à cette compétition.")
    db.delete(competition)
    db.commit()
    audit.record(db, "competition.delete", user_id=user.id, entity="competition",
                 entity_id=str(competition_id))
