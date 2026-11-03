"""Équipes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.api.v1._helpers import commit_or_conflict, conflict, not_found
from app.core import deps
from app.models.match import Match
from app.models.reference import Team
from app.schemas.common import Page
from app.schemas.reference import TeamCreate, TeamRead, TeamUpdate
from app.services import audit

router = APIRouter(
    prefix="/teams",
    tags=["Équipes"],
    dependencies=[Depends(deps.get_auth_context), Depends(deps.verify_csrf)],
)


@router.get("", response_model=Page[TeamRead], summary="Lister les équipes")
def list_teams(
    db: deps.DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    search: Annotated[str | None, Query(max_length=120)] = None,
    sport_id: UUID | None = None,
) -> Page[TeamRead]:
    conditions: list[ColumnElement[bool]] = []
    if search:
        conditions.append(Team.name.ilike(f"%{search}%"))
    if sport_id:
        conditions.append(Team.sport_id == sport_id)

    total = db.scalar(select(func.count()).select_from(Team).where(*conditions)) or 0
    items = db.scalars(
        select(Team)
        .where(*conditions)
        .order_by(Team.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(
        items=[TeamRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "", response_model=TeamRead, status_code=status.HTTP_201_CREATED, summary="Créer une équipe"
)
def create_team(payload: TeamCreate, db: deps.DbSession, user: deps.CurrentUser) -> Team:
    team = Team(**payload.model_dump())
    db.add(team)
    commit_or_conflict(db, "Une équipe portant ce nom existe déjà pour ce sport.")
    db.refresh(team)
    audit.record(db, "team.create", user_id=user.id, entity="team", entity_id=str(team.id),
                 payload=payload.model_dump(mode="json"))
    return team


def _get(db: Session, team_id: UUID) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        not_found("Équipe introuvable.")
    return team


@router.get("/{team_id}", response_model=TeamRead, summary="Détail d'une équipe")
def get_team(team_id: UUID, db: deps.DbSession) -> Team:
    return _get(db, team_id)


@router.patch("/{team_id}", response_model=TeamRead, summary="Modifier une équipe")
def update_team(
    team_id: UUID, payload: TeamUpdate, db: deps.DbSession, user: deps.CurrentUser
) -> Team:
    team = _get(db, team_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(team, field, value)
    commit_or_conflict(db, "Une équipe portant ce nom existe déjà pour ce sport.")
    db.refresh(team)
    audit.record(db, "team.update", user_id=user.id, entity="team", entity_id=str(team.id),
                 payload=payload.model_dump(exclude_unset=True, mode="json"))
    return team


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Supprimer une équipe")
def delete_team(team_id: UUID, db: deps.DbSession, user: deps.CurrentUser) -> None:
    team = _get(db, team_id)
    used = db.scalar(
        select(func.count())
        .select_from(Match)
        .where(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
    )
    if used:
        conflict("Impossible de supprimer : cette équipe figure dans des rencontres.")
    db.delete(team)
    db.commit()
    audit.record(db, "team.delete", user_id=user.id, entity="team", entity_id=str(team_id))
