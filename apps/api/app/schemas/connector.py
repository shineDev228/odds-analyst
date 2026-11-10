"""Schémas des connecteurs de données."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ProviderQuotaRead(BaseModel):
    used: int
    remaining: int | None
    limit: int | None
    reset_at: datetime | None


class ProviderStatusRead(BaseModel):
    provider: str
    label: str
    configured: bool
    role: str
    quota: ProviderQuotaRead
    last_sync_at: datetime | None
    documentation_url: str


class ConnectorLinkCreate(BaseModel):
    provider: str = Field(pattern="^(bigballsdata|the_odds_api|football_data)$")
    competition_id: UUID
    season_id: UUID
    external_league_id: str = Field(min_length=1, max_length=200)
    external_season: str = Field(min_length=1, max_length=40)
    is_enabled: bool = True


class ConnectorLinkUpdate(BaseModel):
    is_enabled: bool


class ConnectorLinkRead(ORMModel):
    id: UUID
    provider: str
    competition_id: UUID
    season_id: UUID
    external_league_id: str
    external_season: str
    is_enabled: bool
    last_fixtures_sync_at: datetime | None
    last_stats_sync_at: datetime | None
    last_odds_sync_at: datetime | None
    competition_name: str | None = None
    season_label: str | None = None


class SyncCounts(BaseModel):
    received: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    conflicts: int = 0
    ignored: int = 0


class SyncRunRead(ORMModel):
    id: UUID
    provider: str
    operation: str
    status: str
    link_id: UUID | None
    params: dict
    summary: dict
    requests_used: int
    credits_used: int
    quota_remaining: int | None
    error_message: str | None
    expires_at: datetime | None
    applied_at: datetime | None
    created_at: datetime


class FixturesPreviewRead(BaseModel):
    run_id: UUID
    provider: str
    operation: str
    status: str
    expires_at: datetime | None
    quota: ProviderQuotaRead
    counts: SyncCounts
    teams_to_create: list[dict]
    conflicts: list[str]
    warnings: list[str]


class ApplyPreviewRead(BaseModel):
    run_id: UUID
    status: str
    counts: SyncCounts


class StatsCandidateRead(BaseModel):
    match_id: UUID
    label: str
    kickoff_at: datetime
    status: str


class StatsPreviewRead(BaseModel):
    provider: str
    candidates: list[StatsCandidateRead]
    cost: int
    budget_remaining: int


class StatsApplyRequest(BaseModel):
    match_ids: list[UUID] = Field(min_length=1, max_length=10)


class StatsApplyResult(BaseModel):
    match_id: UUID
    status: str
    message: str | None = None


class StatsApplyRead(BaseModel):
    results: list[StatsApplyResult]
    created: int
    conflicts: int
    ignored: int


class OddsEventRead(BaseModel):
    event_id: str
    home_team: str
    away_team: str
    commence_time: datetime
    match_id: UUID | None
    match_label: str | None


class OddsEventsRead(BaseModel):
    matched: list[OddsEventRead]
    unmatched: list[OddsEventRead]
    bookmaker: str


class OddsPreviewRead(BaseModel):
    run_id: UUID
    provider: str
    operation: str
    status: str
    expires_at: datetime | None
    quota: ProviderQuotaRead
    counts: SyncCounts
    bookmaker: str
    warnings: list[str]


class ExtendedOddsRequest(BaseModel):
    match_ids: list[UUID] = Field(min_length=1, max_length=20)


class EventLinkRequest(BaseModel):
    match_id: UUID


class DiscoveredCompetitionRead(BaseModel):
    external_id: str
    name: str
    country: str | None = None


class ProviderUsageRead(BaseModel):
    provider: str
    period_kind: str
    period_start: str
    used: int
    limit: int
    remaining: int
    reset_at: datetime | None


class ConnectorOverviewRead(BaseModel):
    providers: list[ProviderStatusRead]
    usage: list[ProviderUsageRead]
    links: list[ConnectorLinkRead]
