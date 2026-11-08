"""Tableau de bord : indicateurs synthétiques."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core import deps
from app.models.match import Match, MatchStatus
from app.models.reference import Competition, Season, Team
from app.schemas.match import MatchListItem

router = APIRouter(
    prefix="/dashboard",
    tags=["Tableau de bord"],
    dependencies=[Depends(deps.get_auth_context), Depends(deps.verify_csrf)],
)

_LOAD = (
    selectinload(Match.home_team),
    selectinload(Match.away_team),
    selectinload(Match.season)
    .selectinload(Season.competition)
    .selectinload(Competition.sport),
)


class DashboardSummary(BaseModel):
    competitions: int
    teams: int
    matches: int
    matchs_a_venir: int
    matchs_termines: int
    prochaines_rencontres: list[MatchListItem]
    derniers_resultats: list[MatchListItem]
    avertissement: str


def _item(match: Match) -> MatchListItem:
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
    )


@router.get("/summary", response_model=DashboardSummary, summary="Indicateurs du tableau de bord")
def summary(db: deps.DbSession) -> DashboardSummary:
    now = datetime.now(UTC)
    horizon = now + timedelta(days=14)

    upcoming = db.scalars(
        select(Match)
        .options(*_LOAD)
        .where(Match.status == MatchStatus.PROGRAMME, Match.kickoff_at >= now)
        .order_by(Match.kickoff_at.asc())
        .limit(5)
    ).all()

    recent = db.scalars(
        select(Match)
        .options(*_LOAD)
        .where(Match.status == MatchStatus.TERMINE)
        .order_by(Match.kickoff_at.desc())
        .limit(5)
    ).all()

    return DashboardSummary(
        competitions=db.scalar(select(func.count()).select_from(Competition)) or 0,
        teams=db.scalar(select(func.count()).select_from(Team)) or 0,
        matches=db.scalar(select(func.count()).select_from(Match)) or 0,
        matchs_a_venir=db.scalar(
            select(func.count())
            .select_from(Match)
            .where(Match.status == MatchStatus.PROGRAMME, Match.kickoff_at <= horizon)
        )
        or 0,
        matchs_termines=db.scalar(
            select(func.count()).select_from(Match).where(Match.status == MatchStatus.TERMINE)
        )
        or 0,
        prochaines_rencontres=[_item(m) for m in upcoming],
        derniers_resultats=[_item(m) for m in recent],
        avertissement=(
            "Outil d'analyse statistique. Aucune sélection n'est présentée comme certaine "
            "et aucun pari n'est placé automatiquement."
        ),
    )
