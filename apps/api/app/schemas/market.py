"""Schémas des marchés, sélections et cotes."""

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.market import MarketSubject
from app.schemas.common import ORMModel

PARIS = ZoneInfo("Europe/Paris")


def _normalize_datetime(value: datetime) -> datetime:
    """Une date sans fuseau est interprétée comme heure de Paris."""
    if value.tzinfo is None:
        return value.replace(tzinfo=PARIS).astimezone(UTC)
    return value.astimezone(UTC)


class SelectionTemplate(BaseModel):
    code: str
    label: str


class MarketTemplateRead(ORMModel):
    code: str
    sport_code: str | None
    name: str
    family: str
    period: str
    subject: MarketSubject
    line_kind: str
    selection_templates: list[SelectionTemplate]
    description: str | None
    is_active: bool


class SelectionInput(BaseModel):
    code: str | None = Field(default=None, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    line: float | None = None
    decimal_odds: float | None = Field(default=None, gt=1, le=10000)


class MarketCreate(BaseModel):
    template_code: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, min_length=2, max_length=160)
    family: str | None = Field(default=None, min_length=2, max_length=80)
    period: str = Field(default="match", min_length=2, max_length=40)
    subject: MarketSubject = MarketSubject.MATCH
    subject_team_id: UUID | None = None
    subject_player: str | None = Field(default=None, max_length=120)
    line: float | None = None
    line2: float | None = None
    selections: list[SelectionInput] | None = Field(default=None, max_length=60)
    bookmaker: str = Field(default="1xBet", min_length=1, max_length=80)
    source: str = Field(default="manuel", min_length=1, max_length=40)
    captured_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("captured_at")
    @classmethod
    def _tz(cls, value: datetime | None) -> datetime | None:
        return _normalize_datetime(value) if value else None

    @model_validator(mode="after")
    def _consistency(self) -> "MarketCreate":
        if self.subject == MarketSubject.TEAM and self.subject_team_id is None:
            raise ValueError("Un marché d'équipe doit préciser l'équipe concernée.")
        if self.subject == MarketSubject.PLAYER and not self.subject_player:
            raise ValueError("Un marché joueur doit préciser le nom du joueur.")
        if self.subject == MarketSubject.MATCH and (
            self.subject_team_id is not None or self.subject_player
        ):
            raise ValueError("Un marché de match ne doit pas désigner d'équipe ni de joueur.")
        if self.selections is not None:
            codes = [item.code or item.label.strip().lower() for item in self.selections]
            if len(codes) != len(set(codes)):
                raise ValueError("Les sélections d'un marché doivent être distinctes.")
        if not self.template_code and (not self.name or not self.family):
            raise ValueError("Un marché personnalisé doit préciser son nom et sa famille.")
        return self


class MarketUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    line: float | None = None
    line2: float | None = None
    notes: str | None = Field(default=None, max_length=1000)


class OddsCreate(BaseModel):
    decimal_odds: float = Field(gt=1, le=10000)
    captured_at: datetime | None = None
    bookmaker: str = Field(default="1xBet", min_length=1, max_length=80)
    source: str = Field(default="manuel", min_length=1, max_length=40)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("captured_at")
    @classmethod
    def _tz(cls, value: datetime | None) -> datetime | None:
        return _normalize_datetime(value) if value else None


class OddsRead(ORMModel):
    id: UUID
    selection_id: UUID
    decimal_odds: float
    captured_at: datetime
    bookmaker: str
    source: str
    note: str | None

    @field_validator("captured_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class SelectionRead(BaseModel):
    id: UUID
    market_id: UUID
    code: str
    label: str
    line: float | None
    sort_order: int
    latest_odds: float | None
    latest_captured_at: datetime | None
    implied_probability: float | None
    fair_probability: float | None
    fair_odds: float | None
    odds_count: int
    history: list[OddsRead]


class MarketRead(BaseModel):
    id: UUID
    match_id: UUID
    template_code: str | None
    name: str
    family: str
    period: str
    subject: MarketSubject
    subject_team_id: UUID | None
    subject_team_name: str | None
    subject_player: str | None
    line: float | None
    line2: float | None
    is_custom: bool
    notes: str | None
    created_at: datetime
    latest_captured_at: datetime | None
    overround_percent: float | None
    implied_probability_total: float | None
    is_complete: bool
    selections: list[SelectionRead]

    @field_validator("created_at", "latest_captured_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: datetime | None) -> datetime | None:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
