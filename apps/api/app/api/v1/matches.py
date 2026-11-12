"""Rencontres et statistiques."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.v1._helpers import conflict, not_found
from app.core import deps
from app.models.market import Market, MarketSubject, OddsSnapshot, Selection
from app.models.match import Match, MatchStatus, TeamMatchStats
from app.models.reference import Competition, Season, Team
from app.schemas.common import Page
from app.schemas.match import (
    MatchCreate,
    MatchDetail,
    MatchListItem,
    MatchUpdate,
    Odds1x2Read,
    StatsRead,
    StatsUpsert,
    TeamRef,
)
from app.services import audit

router = APIRouter(
    prefix="/matches",
    tags=["Rencontres"],
    dependencies=[Depends(deps.get_auth_context), Depends(deps.verify_csrf)],
)

_LOAD_OPTIONS = (
    selectinload(Match.home_team),
    selectinload(Match.away_team),
    selectinload(Match.season)
    .selectinload(Season.competition)
    .selectinload(Competition.sport),
    selectinload(Match.stats),
)


def _to_list_item(match: Match, odds: Odds1x2Read | None = None) -> MatchListItem:
    return MatchListItem(
        id=match.id,
        season_id=match.season_id,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        kickoff_at=match.kickoff_at,
        status=match.status,
        home_score=match.home_score,
        away_score=match.away_score,
        half_time_home_score=match.half_time_home_score,
        half_time_away_score=match.half_time_away_score,
        venue=match.venue,
        referee=match.referee,
        notes=match.notes,
        home_team_name=match.home_team.name,
        away_team_name=match.away_team.name,
        competition_name=match.season.competition.name,
        season_label=match.season.label,
        sport_id=match.season.competition.sport_id,
        sport_code=match.season.competition.sport.code,
        odds_1x2=odds,
    )


def _odds_1x2(db: Session, match_ids: list[UUID]) -> dict[UUID, Odds1x2Read]:
    """Dernières cotes 1X2 des rencontres demandées, en une seule requête."""
    if not match_ids:
        return {}
    latest = (
        select(
            OddsSnapshot.selection_id.label("selection_id"),
            func.max(OddsSnapshot.captured_at).label("captured_at"),
        )
        .join(Selection, Selection.id == OddsSnapshot.selection_id)
        .join(Market, Market.id == Selection.market_id)
        .where(
            Market.match_id.in_(match_ids),
            Market.family == "resultat",
            Market.period == "match",
            Market.subject == MarketSubject.MATCH,
            Selection.code.in_(("1", "X", "2")),
        )
        .group_by(OddsSnapshot.selection_id)
        .subquery()
    )
    rows = db.execute(
        select(Market.match_id, Selection.code, OddsSnapshot.decimal_odds)
        .join(Selection, Selection.market_id == Market.id)
        .join(OddsSnapshot, OddsSnapshot.selection_id == Selection.id)
        .join(
            latest,
            (latest.c.selection_id == OddsSnapshot.selection_id)
            & (latest.c.captured_at == OddsSnapshot.captured_at),
        )
        .where(
            Market.match_id.in_(match_ids),
            Market.family == "resultat",
            Market.period == "match",
            Market.subject == MarketSubject.MATCH,
            Selection.code.in_(("1", "X", "2")),
        )
    ).all()

    codes: dict[UUID, dict[str, float]] = {}
    for match_id, code, odds in rows:
        codes.setdefault(match_id, {})[code] = float(odds)
    return {
        match_id: Odds1x2Read(
            home=values.get("1"),
            draw=values.get("X"),
            away=values.get("2"),
        )
        for match_id, values in codes.items()
    }


def _to_detail(match: Match) -> MatchDetail:
    base = _to_list_item(match).model_dump()
    return MatchDetail(
        **base,
        home_team=TeamRef.model_validate(match.home_team),
        away_team=TeamRef.model_validate(match.away_team),
        stats=[StatsRead.model_validate(s) for s in match.stats],
    )


def _load(db: Session, match_id: UUID) -> Match:
    match = db.scalar(
        select(Match)
        .options(*_LOAD_OPTIONS)
        .where(Match.id == match_id)
        .execution_options(populate_existing=True)
    )
    if match is None:
        not_found("Rencontre introuvable.")
    return match


@router.get("", response_model=Page[MatchListItem], summary="Lister les rencontres")
def list_matches(
    db: deps.DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    season_id: UUID | None = None,
    competition_id: UUID | None = None,
    team_id: UUID | None = None,
    match_status: Annotated[MatchStatus | None, Query(alias="status")] = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Page[MatchListItem]:
    conditions = []
    if season_id:
        conditions.append(Match.season_id == season_id)
    if competition_id:
        conditions.append(
            Match.season_id.in_(select(Season.id).where(Season.competition_id == competition_id))
        )
    if team_id:
        conditions.append(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
    if match_status:
        conditions.append(Match.status == match_status)
    if date_from:
        conditions.append(Match.kickoff_at >= date_from)
    if date_to:
        conditions.append(Match.kickoff_at <= date_to)

    total = db.scalar(select(func.count()).select_from(Match).where(*conditions)) or 0

    ordering = Match.kickoff_at.asc() if order == "asc" else Match.kickoff_at.desc()
    matches = db.scalars(
        select(Match)
        .options(*_LOAD_OPTIONS)
        .where(*conditions)
        .order_by(ordering)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    odds = _odds_1x2(db, [match.id for match in matches])
    return Page(
        items=[_to_list_item(m, odds.get(m.id)) for m in matches],
        total=total,
        page=page,
        page_size=page_size,
    )


def _check_teams(db: Session, season: Season, home_id: UUID, away_id: UUID) -> None:
    if home_id == away_id:
        conflict("Les deux équipes doivent être différentes.")

    competition = db.get(Competition, season.competition_id)
    home = db.get(Team, home_id)
    away = db.get(Team, away_id)
    if home is None or away is None:
        not_found("Équipe introuvable.")
    if competition is not None and (home.sport_id != competition.sport_id
                                   or away.sport_id != competition.sport_id):
        conflict("Les équipes doivent appartenir au même sport que la compétition.")


@router.post(
    "",
    response_model=MatchDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Créer une rencontre",
)
def create_match(
    payload: MatchCreate, db: deps.DbSession, user: deps.CurrentUser
) -> MatchDetail:
    season = db.get(Season, payload.season_id)
    if season is None:
        not_found("Saison introuvable.")
    _check_teams(db, season, payload.home_team_id, payload.away_team_id)

    match = Match(**payload.model_dump())
    db.add(match)
    db.commit()
    db.refresh(match)
    audit.record(db, "match.create", user_id=user.id, entity="match", entity_id=str(match.id),
                 payload=payload.model_dump(mode="json"))
    return _to_detail(_load(db, match.id))


@router.get("/{match_id}", response_model=MatchDetail, summary="Détail d'une rencontre")
def get_match(match_id: UUID, db: deps.DbSession) -> MatchDetail:
    return _to_detail(_load(db, match_id))


@router.patch("/{match_id}", response_model=MatchDetail, summary="Modifier une rencontre")
def update_match(
    match_id: UUID, payload: MatchUpdate, db: deps.DbSession, user: deps.CurrentUser
) -> MatchDetail:
    match = _load(db, match_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(match, field, value)
    db.commit()
    audit.record(db, "match.update", user_id=user.id, entity="match", entity_id=str(match_id),
                 payload=payload.model_dump(exclude_unset=True, mode="json"))
    return _to_detail(_load(db, match_id))


@router.delete(
    "/{match_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Supprimer une rencontre"
)
def delete_match(match_id: UUID, db: deps.DbSession, user: deps.CurrentUser) -> None:
    match = _load(db, match_id)
    db.delete(match)
    db.commit()
    audit.record(db, "match.delete", user_id=user.id, entity="match", entity_id=str(match_id))


@router.get(
    "/{match_id}/stats",
    response_model=list[StatsRead],
    summary="Statistiques d'une rencontre",
)
def get_match_stats(match_id: UUID, db: deps.DbSession) -> list[StatsRead]:
    match = _load(db, match_id)
    return [StatsRead.model_validate(s) for s in match.stats]


@router.put(
    "/{match_id}/stats",
    response_model=list[StatsRead],
    summary="Enregistrer les statistiques d'une rencontre",
)
def upsert_match_stats(
    match_id: UUID,
    payload: list[StatsUpsert],
    db: deps.DbSession,
    user: deps.CurrentUser,
) -> list[StatsRead]:
    match = _load(db, match_id)
    expected = {match.home_team_id, match.away_team_id}
    provided = {item.team_id for item in payload}
    if provided != expected or len(payload) != 2:
        conflict("Les statistiques doivent concerner exactement les deux équipes de la rencontre.")
    for item in payload:
        if item.is_home != (item.team_id == match.home_team_id):
            conflict("L'indicateur domicile/extérieur est incohérent avec la rencontre.")

    existing = {s.team_id: s for s in match.stats}
    for item in payload:
        data = item.model_dump()
        row = existing.get(item.team_id)
        if row is None:
            db.add(TeamMatchStats(match_id=match_id, **data))
        else:
            for field, value in data.items():
                setattr(row, field, value)

    db.commit()
    audit.record(db, "match.stats", user_id=user.id, entity="match", entity_id=str(match_id),
                 payload={"equipes": len(payload)})
    return [StatsRead.model_validate(s) for s in _load(db, match_id).stats]
