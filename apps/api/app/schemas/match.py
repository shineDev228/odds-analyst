"""Schémas des rencontres et des statistiques."""

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.match import MatchStatus
from app.schemas.common import ORMModel

PARIS = ZoneInfo("Europe/Paris")


def _normalize_datetime(value: datetime) -> datetime:
    """Une date sans fuseau est interprétée comme heure de Paris."""
    if value.tzinfo is None:
        return value.replace(tzinfo=PARIS).astimezone(UTC)
    return value.astimezone(UTC)


class MatchCreate(BaseModel):
    season_id: UUID
    home_team_id: UUID
    away_team_id: UUID
    kickoff_at: datetime
    status: MatchStatus = MatchStatus.PROGRAMME
    venue: str | None = Field(default=None, max_length=120)
    referee: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("kickoff_at")
    @classmethod
    def _tz(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)

    @model_validator(mode="after")
    def _distinct_teams(self) -> "MatchCreate":
        if self.home_team_id == self.away_team_id:
            raise ValueError(
                "L'équipe à domicile et l'équipe à l'extérieur doivent être différentes."
            )
        return self


class MatchUpdate(BaseModel):
    kickoff_at: datetime | None = None
    status: MatchStatus | None = None
    home_score: int | None = Field(default=None, ge=0, le=99)
    away_score: int | None = Field(default=None, ge=0, le=99)
    half_time_home_score: int | None = Field(default=None, ge=0, le=99)
    half_time_away_score: int | None = Field(default=None, ge=0, le=99)
    venue: str | None = Field(default=None, max_length=120)
    referee: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("kickoff_at")
    @classmethod
    def _tz(cls, value: datetime | None) -> datetime | None:
        return _normalize_datetime(value) if value else None


class TeamRef(ORMModel):
    id: UUID
    name: str
    short_name: str | None


class MatchRead(ORMModel):
    id: UUID
    season_id: UUID
    home_team_id: UUID
    away_team_id: UUID
    kickoff_at: datetime
    status: MatchStatus
    home_score: int | None
    away_score: int | None
    half_time_home_score: int | None
    half_time_away_score: int | None
    venue: str | None
    referee: str | None
    notes: str | None

    @field_validator("kickoff_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        """Garantit un horodatage avec fuseau, même si le SGBD renvoie une date naïve."""
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Odds1x2Read(BaseModel):
    """Dernières cotes du marché 1X2, si elles existent."""

    home: float | None = None
    draw: float | None = None
    away: float | None = None


class MatchListItem(MatchRead):
    home_team_name: str
    away_team_name: str
    competition_name: str
    season_label: str
    sport_id: UUID
    sport_code: str
    odds_1x2: Odds1x2Read | None = None


class StatsUpsert(BaseModel):
    team_id: UUID
    is_home: bool
    goals_for: int | None = Field(default=None, ge=0, le=99)
    goals_against: int | None = Field(default=None, ge=0, le=99)
    shots: int | None = Field(default=None, ge=0, le=99)
    shots_on_target: int | None = Field(default=None, ge=0, le=99)
    possession: float | None = Field(default=None, ge=0, le=100)
    corners: int | None = Field(default=None, ge=0, le=99)
    yellow_cards: int | None = Field(default=None, ge=0, le=99)
    red_cards: int | None = Field(default=None, ge=0, le=20)
    expected_goals: float | None = Field(default=None, ge=0, le=20)


class StatsRead(ORMModel):
    id: UUID
    match_id: UUID
    team_id: UUID
    is_home: bool
    goals_for: int | None
    goals_against: int | None
    shots: int | None
    shots_on_target: int | None
    possession: float | None
    corners: int | None
    yellow_cards: int | None
    red_cards: int | None
    expected_goals: float | None


class MatchDetail(MatchListItem):
    home_team: TeamRef
    away_team: TeamRef
    stats: list[StatsRead]
