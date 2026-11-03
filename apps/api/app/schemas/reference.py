"""Schémas du référentiel sportif."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import ORMModel


class SportRead(ORMModel):
    id: UUID
    code: str
    name: str


class CompetitionCreate(BaseModel):
    sport_id: UUID
    name: str = Field(min_length=2, max_length=120)
    country: str | None = Field(default=None, max_length=80)
    tier: int | None = Field(default=None, ge=1, le=10)

    @field_validator("name", "country")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class CompetitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    country: str | None = Field(default=None, max_length=80)
    tier: int | None = Field(default=None, ge=1, le=10)
    is_active: bool | None = None


class CompetitionRead(ORMModel):
    id: UUID
    sport_id: UUID
    name: str
    country: str | None
    tier: int | None
    is_active: bool


class SeasonCreate(BaseModel):
    competition_id: UUID
    label: str = Field(min_length=2, max_length=40)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = True

    @model_validator(mode="after")
    def _check_dates(self) -> "SeasonCreate":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("La date de fin doit être postérieure à la date de début.")
        return self


class SeasonUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=2, max_length=40)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool | None = None


class SeasonRead(ORMModel):
    id: UUID
    competition_id: UUID
    label: str
    start_date: date | None
    end_date: date | None
    is_current: bool


class TeamCreate(BaseModel):
    sport_id: UUID
    name: str = Field(min_length=2, max_length=120)
    short_name: str | None = Field(default=None, max_length=40)
    country: str | None = Field(default=None, max_length=80)

    @field_validator("name", "short_name", "country")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    short_name: str | None = Field(default=None, max_length=40)
    country: str | None = Field(default=None, max_length=80)


class TeamRead(ORMModel):
    id: UUID
    sport_id: UUID
    name: str
    short_name: str | None
    country: str | None
