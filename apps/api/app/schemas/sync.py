"""Schémas de la page Synchronisation (une seule source : BigBallsData)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class SyncQuotaRead(BaseModel):
    used: int
    remaining: int | None
    limit: int | None
    reset_at: datetime | None


class SyncLeagueRead(BaseModel):
    code: str
    name: str
    season_label: str | None
    finished: int
    upcoming: int
    last_sync_at: datetime | None
    last_status: str | None


class SyncTotalsRead(BaseModel):
    matches: int
    teams: int
    stats_rows: int
    xg_rows: int


class SyncRunRead(ORMModel):
    id: UUID
    provider: str
    operation: str
    status: str
    params: dict
    summary: dict
    requests_used: int
    credits_used: int
    quota_remaining: int | None
    error_message: str | None
    applied_at: datetime | None
    created_at: datetime


class SyncOverviewRead(BaseModel):
    provider: str
    configured: bool
    season: str
    quota: SyncQuotaRead
    totals: SyncTotalsRead
    leagues: list[SyncLeagueRead]
    runs: list[SyncRunRead]


class SyncRequest(BaseModel):
    """Compétitions à importer ; vide = les sept compétitions suivies."""

    leagues: list[str] | None = Field(default=None, max_length=7)
    include_stats: bool = False
    include_standings: bool = False
    stats_limit: int = Field(default=20, ge=0, le=200)


class LeagueReportRead(BaseModel):
    code: str
    name: str
    status: str
    requests: int
    matches: int
    created: int
    updated: int
    unchanged: int
    ignored: int
    teams_created: int
    stats_requested: int
    stats_written: int
    standings_written: int
    warnings: list[str]
    error: str | None


class SyncReportRead(BaseModel):
    provider: str
    status: str
    season: str
    requests: int
    quota_remaining: int | None
    error: str | None
    totals: dict[str, int]
    leagues: list[LeagueReportRead]
