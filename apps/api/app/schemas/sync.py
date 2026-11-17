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
    # Rencontres terminées pour lesquelles le fournisseur n'a rien renvoyé.
    stats_missing: int = 0
    # Fiches en double renvoyées par le fournisseur, ignorées à l'import.
    duplicates: int = 0
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


class OddsCostsRead(BaseModel):
    """Coût affiché avant chaque appel, en crédits du fournisseur."""

    competition: int
    event: int
    extended_window_hours: int
    extended_max_events: int


class OddsTotalsRead(BaseModel):
    markets: int
    odds_rows: int
    active_links: int


class OddsOverviewRead(BaseModel):
    """État de la source de cotes : quota mensuel, coûts, couverture."""

    provider: str
    configured: bool
    quota: SyncQuotaRead
    costs: OddsCostsRead
    totals: OddsTotalsRead
    upcoming: dict[str, int]
    last_run: SyncRunRead | None


class OddsRequest(BaseModel):
    """Compétitions à coter ; vide = les sept compétitions suivies."""

    leagues: list[str] | None = Field(default=None, max_length=7)
    include_extended: bool = True
    extended_limit: int = Field(default=30, ge=0, le=30)


class OddsLeagueReportRead(BaseModel):
    code: str
    name: str
    status: str
    events: int
    matched: int
    ambiguous: int
    unmatched: int
    links_created: int
    links_reused: int
    links_deactivated: int
    bookmaker_missing: int
    markets_written: int
    snapshots_written: int
    manual_kept: int
    extended_events: int
    credits: int
    warnings: list[str]
    error: str | None


class OddsReportRead(BaseModel):
    provider: str
    status: str
    credits_used: int
    requests: int
    quota_remaining: int | None
    error: str | None
    totals: dict[str, int]
    leagues: list[OddsLeagueReportRead]


class OddsPreviewEventRead(BaseModel):
    event_id: str
    home_team: str
    away_team: str
    commence_at: datetime
    decision: str
    method: str | None
    confidence: float
    margin: float
    match_id: UUID | None
    match_label: str | None


class OddsPreviewLeagueRead(BaseModel):
    code: str
    name: str
    status: str
    events: int
    matched: int
    ambiguous: int
    unmatched: int
    credits: int
    items: list[OddsPreviewEventRead]
    error: str | None


class OddsPreviewRead(BaseModel):
    provider: str
    status: str
    credits_estimated: int
    quota_remaining: int | None
    error: str | None
    leagues: list[OddsPreviewLeagueRead]
