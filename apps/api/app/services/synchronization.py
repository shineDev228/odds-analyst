"""Synchronisation BigBallsData : import unique et rejouable.

Une seule source de faits. Une passe par compétition, paginée, idempotente :
relancer la même journée ne crée aucun doublon. Les statistiques et le
classement sont facultatifs pour garder chaque appel HTTP borné ; une seconde
passe termine ce que la première a laissé.

Aucune clé n'est journalisée : seuls les noms de champs et les compteurs
apparaissent dans `sync_runs`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.base import (
    BudgetExceededError,
    ConnectorError,
    MissingKeyError,
    ProviderRateLimitError,
)
from app.connectors.bigballsdata.client import BigBallsDataClient
from app.connectors.bigballsdata.importer import (
    PROVIDER,
    ImportConflict,
    apply_standings,
    apply_statistics,
    get_football,
    upsert_competition,
    upsert_match,
    upsert_season,
    upsert_team,
)
from app.connectors.bigballsdata.mapping import (
    map_league,
    map_match,
    map_standing_row,
    map_statistics,
)
from app.connectors.http import HttpClient
from app.connectors.quota import consume, ensure_budget, snapshot
from app.core.config import settings
from app.models.connector import SyncOperation, SyncRun, SyncStatus
from app.models.match import Match, MatchStatus, TeamMatchStats
from app.models.reference import Competition, Season, Team

TRACKED_LEAGUES = ("ligue1", "laliga", "epl", "seriea", "bundesliga", "ucl", "mls")
PAGE_SIZE = 200
MAX_PAGES = 30
STATS_MAX = 200
RATE_LIMIT_ATTEMPTS = 3
RATE_LIMIT_DELAY_SECONDS = 5.0
# 75 requêtes/minute : sous la limite de 100, avec une marge pour les réessais.
MIN_INTERVAL_SECONDS = 0.8


@dataclass(slots=True)
class LeagueReport:
    code: str
    name: str
    status: str = "applied"
    requests: int = 0
    matches: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    ignored: int = 0
    teams_created: int = 0
    stats_requested: int = 0
    stats_written: int = 0
    standings_written: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "status": self.status,
            "requests": self.requests,
            "matches": self.matches,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "ignored": self.ignored,
            "teams_created": self.teams_created,
            "stats_requested": self.stats_requested,
            "stats_written": self.stats_written,
            "standings_written": self.standings_written,
            "warnings": list(self.warnings),
            "error": self.error,
        }


@dataclass(slots=True)
class SyncReport:
    provider: str = PROVIDER
    status: str = "applied"
    season: str = ""
    requests: int = 0
    quota_remaining: int | None = None
    error: str | None = None
    leagues: list[LeagueReport] = field(default_factory=list)

    @property
    def totals(self) -> dict[str, int]:
        return {
            "requests": sum(item.requests for item in self.leagues),
            "matches": sum(item.matches for item in self.leagues),
            "created": sum(item.created for item in self.leagues),
            "updated": sum(item.updated for item in self.leagues),
            "unchanged": sum(item.unchanged for item in self.leagues),
            "ignored": sum(item.ignored for item in self.leagues),
            "teams_created": sum(item.teams_created for item in self.leagues),
            "stats_requested": sum(item.stats_requested for item in self.leagues),
            "stats_written": sum(item.stats_written for item in self.leagues),
            "standings_written": sum(item.standings_written for item in self.leagues),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "season": self.season,
            "requests": self.requests,
            "quota_remaining": self.quota_remaining,
            "error": self.error,
            "totals": self.totals,
            "leagues": [item.as_dict() for item in self.leagues],
        }


def make_client() -> BigBallsDataClient:
    """Construit le client à partir du `.env` ; la clé n'est jamais journalisée."""
    if not settings.bigballsdata_key:
        raise MissingKeyError(
            "Clé BigBallsData absente. Renseignez BIGBALLSDATA_KEY dans .env "
            "puis redémarrez l'API."
        )
    http = HttpClient(
        timeout=settings.connector_timeout_seconds,
        max_retries=settings.connector_max_retries,
        min_interval=MIN_INTERVAL_SECONDS,
    )
    return BigBallsDataClient(
        api_key=settings.bigballsdata_key,
        base_url=settings.bigballsdata_base_url,
        http=http,
    )


def run_sync(
    db: Session,
    *,
    leagues: list[str] | None = None,
    include_stats: bool = False,
    include_standings: bool = False,
    stats_limit: int = 20,
    now: datetime | None = None,
    client: Any | None = None,
    sleep: Any = time.sleep,
) -> SyncReport:
    """Importe les compétitions demandées et journalise chaque passe.

    Ne valide pas la transaction : l'appelant décide du ``commit``.
    """
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    season_external = settings.bigballsdata_season
    selected = [code for code in (leagues or TRACKED_LEAGUES) if code in TRACKED_LEAGUES]
    report = SyncReport(season=season_external)
    if not selected:
        report.status = "empty"
        return report

    own_client = client is None
    connector = client
    try:
        if connector is None:
            try:
                connector = make_client()
            except ConnectorError as exc:
                report.status = "failed"
                report.error = exc.message
                return report
        try:
            catalogue = _league_catalogue(db, connector, report)
        except ConnectorError as exc:
            report.status = "failed"
            report.error = exc.message
            return report

        stopped = False
        for code in selected:
            info = catalogue.get(code)
            if info is None:
                report.leagues.append(
                    LeagueReport(
                        code=code,
                        name=code,
                        status="skipped",
                        error="Compétition absente du catalogue du fournisseur.",
                    )
                )
                continue
            if stopped:
                report.leagues.append(
                    LeagueReport(
                        code=code,
                        name=str(info["name"] or code),
                        status="skipped",
                        error="Passe arrêtée : quota ou limitation atteinte.",
                    )
                )
                continue

            item = LeagueReport(code=code, name=str(info["name"] or code))
            try:
                _sync_league(
                    db,
                    connector,
                    item=item,
                    info=info,
                    season_external=season_external,
                    include_stats=include_stats,
                    include_standings=include_standings,
                    stats_limit=min(max(stats_limit, 0), STATS_MAX),
                    moment=moment,
                    sleep=sleep,
                )
            except (BudgetExceededError, ProviderRateLimitError) as exc:
                stopped = True
                item.status = "failed"
                item.error = exc.message
            except ConnectorError as exc:
                item.status = "failed"
                item.error = exc.message
            except ImportConflict as exc:
                item.status = "failed"
                item.error = str(exc)
            _record_run(db, item, moment)
            report.leagues.append(item)

        if stopped:
            report.status = "partial"
        elif any(item.status == "failed" for item in report.leagues):
            applied = any(item.status == "applied" for item in report.leagues)
            report.status = "partial" if applied else "failed"
        report.requests = 1 + report.totals["requests"]
    finally:
        if own_client and connector is not None:
            connector.close()

    report.quota_remaining = snapshot(db, PROVIDER).remaining
    return report


def _league_catalogue(
    db: Session, client: Any, report: SyncReport
) -> dict[str, dict[str, str | None]]:
    """Une requête pour connaître les noms et pays officiels des compétitions."""
    ensure_budget(db, PROVIDER, 1)
    raw = client.list_leagues()
    consume(db, PROVIDER, 1)
    report.requests += 1
    catalogue: dict[str, dict[str, str | None]] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            info = map_league(entry)
        except ValueError:
            continue
        catalogue[str(info["code"])] = info
    return catalogue


def _sync_league(
    db: Session,
    client: Any,
    *,
    item: LeagueReport,
    info: dict[str, str | None],
    season_external: str,
    include_stats: bool,
    include_standings: bool,
    stats_limit: int,
    moment: datetime,
    sleep: Any,
) -> None:
    sport = get_football(db)
    competition = upsert_competition(
        db,
        sport_id=sport.id,
        code=str(info["code"]),
        name=str(info["name"]),
        country=info.get("country"),
    )
    season = upsert_season(db, competition=competition, external_label=season_external)

    teams: dict[str, Team] = {}
    for status in ("finished", "scheduled"):
        raw = _fetch_matches(
            db,
            client,
            code=item.code,
            season_external=season_external,
            status=status,
            item=item,
            sleep=sleep,
        )
        for payload in raw:
            if not isinstance(payload, dict):
                item.ignored += 1
                continue
            try:
                normalized = map_match(
                    payload,
                    competition_external_id=item.code,
                    season_label=season_external,
                )
            except (KeyError, TypeError, ValueError):
                item.ignored += 1
                continue
            item.matches += 1
            home, home_created = _team(db, sport.id, normalized.home, teams)
            away, away_created = _team(db, sport.id, normalized.away, teams)
            item.teams_created += int(home_created) + int(away_created)
            match, action = upsert_match(
                db,
                season=season,
                match=normalized,
                home=home,
                away=away,
                now=moment,
            )
            if action == "created":
                item.created += 1
            elif action == "updated":
                item.updated += 1
            else:
                item.unchanged += 1

            if include_stats:
                _collect_statistics(
                    db,
                    client,
                    item=item,
                    match=match,
                    teams=teams,
                    limit=stats_limit,
                    sleep=sleep,
                )

    if include_stats and stats_limit > 0 and item.stats_requested >= stats_limit:
        item.warnings.append(
            f"Limite de {stats_limit} rencontres statistiques atteinte : relancez la passe."
        )

    if include_standings:
        _collect_standings(
            db,
            client,
            item=item,
            competition=competition,
            season=season,
            season_external=season_external,
            teams=teams,
            moment=moment,
        )


def _team(
    db: Session, sport_id: Any, normalized: Any, cache: dict[str, Team]
) -> tuple[Team, bool]:
    cached = cache.get(normalized.external_id)
    if cached is not None:
        return cached, False
    row, created = upsert_team(db, sport_id=sport_id, team=normalized)
    cache[normalized.external_id] = row
    return row, created


def _fetch_matches(
    db: Session,
    client: Any,
    *,
    code: str,
    season_external: str,
    status: str,
    item: LeagueReport,
    sleep: Any,
) -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = []
    offset = 0
    pages = 0
    while pages < MAX_PAGES:
        page = _fetch_page(
            db,
            client,
            code=code,
            season_external=season_external,
            status=status,
            offset=offset,
            item=item,
            sleep=sleep,
        )
        pages += 1
        raw.extend(entry for entry in page if isinstance(entry, dict))
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    if pages >= MAX_PAGES:
        item.warnings.append(
            f"Pagination arrêtée après {MAX_PAGES} pages : relancez la passe pour poursuivre."
        )
    return raw


def _fetch_page(
    db: Session,
    client: Any,
    *,
    code: str,
    season_external: str,
    status: str,
    offset: int,
    item: LeagueReport,
    sleep: Any,
) -> list[dict[str, Any]]:
    for attempt in range(1, RATE_LIMIT_ATTEMPTS + 1):
        ensure_budget(db, PROVIDER, 1)
        try:
            page = client.list_matches(
                league=code,
                season=season_external,
                limit=PAGE_SIZE,
                offset=offset,
                status=status,
            )
        except BudgetExceededError:
            raise
        except ProviderRateLimitError:
            if attempt >= RATE_LIMIT_ATTEMPTS:
                raise
            sleep(RATE_LIMIT_DELAY_SECONDS * attempt)
            continue
        consume(db, PROVIDER, 1)
        item.requests += 1
        return [entry for entry in page if isinstance(entry, dict)]
    return []


def _collect_statistics(
    db: Session,
    client: Any,
    *,
    item: LeagueReport,
    match: Match,
    teams: dict[str, Team],
    limit: int,
    sleep: Any,
) -> None:
    """Récupère les statistiques d'une rencontre, dans la limite de la passe."""
    if limit <= 0 or item.stats_requested >= limit:
        return
    if match.external_id is None or match.status != MatchStatus.TERMINE:
        return
    existing = db.scalar(
        select(TeamMatchStats.id)
        .where(
            TeamMatchStats.match_id == match.id,
            TeamMatchStats.data_source == PROVIDER,
        )
        .limit(1)
    )
    if existing is not None:
        return
    for attempt in range(1, RATE_LIMIT_ATTEMPTS + 1):
        ensure_budget(db, PROVIDER, 1)
        try:
            payload = client.get_statistics(match.external_id)
        except BudgetExceededError:
            raise
        except ProviderRateLimitError:
            if attempt >= RATE_LIMIT_ATTEMPTS:
                raise
            sleep(RATE_LIMIT_DELAY_SECONDS * attempt)
            continue
        except ConnectorError:
            item.warnings.append(
                f"Statistiques indisponibles pour la rencontre {match.external_id}."
            )
            return
        consume(db, PROVIDER, 1)
        item.requests += 1
        item.stats_requested += 1
        home_id = match.home_team.external_id or ""
        away_id = match.away_team.external_id or ""
        lines = map_statistics(
            payload,
            match_external_id=str(match.external_id),
            home_id=home_id,
            away_id=away_id,
        )
        counts = apply_statistics(db, match=match, lines=lines, teams=teams)
        item.stats_written += counts.created + counts.updated
        return


def _collect_standings(
    db: Session,
    client: Any,
    *,
    item: LeagueReport,
    competition: Competition,
    season: Season,
    season_external: str,
    teams: dict[str, Team],
    moment: datetime,
) -> None:
    ensure_budget(db, PROVIDER, 1)
    try:
        rows = client.get_standings(league=item.code, season=season_external)
    except ConnectorError as exc:
        item.warnings.append(f"Classement indisponible : {exc.message}")
        return
    consume(db, PROVIDER, 1)
    item.requests += 1
    parsed = []
    for raw in rows:
        try:
            parsed.append(map_standing_row(raw))
        except ValueError:
            continue
    ids = [line.team_external_id for line in parsed]
    known = {
        row.external_id: row
        for row in db.scalars(select(Team).where(Team.external_id.in_(ids))).all()
        if row.external_id
    }
    teams.update(known)
    counts = apply_standings(
        db,
        competition=competition,
        season=season,
        lines=parsed,
        teams=teams,
        now=moment,
    )
    item.standings_written += counts.created + counts.updated


def _record_run(db: Session, item: LeagueReport, moment: datetime) -> None:
    status = SyncStatus.APPLIED.value if item.status == "applied" else SyncStatus.FAILED.value
    info = snapshot(db, PROVIDER)
    db.add(
        SyncRun(
            provider=PROVIDER,
            operation=SyncOperation.FIXTURES.value,
            status=status,
            params={
                "league": item.code,
                "season": settings.bigballsdata_season,
                "page_size": PAGE_SIZE,
            },
            summary={
                "counts": {
                    "received": item.matches,
                    "created": item.created,
                    "updated": item.updated,
                    "unchanged": item.unchanged,
                    "conflicts": 0,
                    "ignored": item.ignored,
                },
                "teams_created": item.teams_created,
                "stats_requested": item.stats_requested,
                "stats_written": item.stats_written,
                "standings_written": item.standings_written,
                "warnings": list(item.warnings),
            },
            requests_used=item.requests,
            credits_used=0,
            quota_remaining=info.remaining,
            error_message=(item.error or "")[:1000] or None,
            applied_at=moment,
        )
    )
    db.flush()


def recent_runs(db: Session, limit: int = 20) -> list[SyncRun]:
    return list(
        db.scalars(select(SyncRun).order_by(SyncRun.created_at.desc()).limit(limit)).all()
    )


def overview(db: Session) -> dict[str, Any]:
    """État lisible pour la page Synchronisation."""
    info = snapshot(db, PROVIDER)
    recent = recent_runs(db, 100)
    last_by_code: dict[str, SyncRun] = {}
    for run in recent:
        code = str((run.params or {}).get("league") or "")
        if code and code not in last_by_code:
            last_by_code[code] = run

    competitions = db.scalars(
        select(Competition).where(Competition.code.in_(TRACKED_LEAGUES))
    ).all()
    by_code = {competition.code: competition for competition in competitions}
    leagues: list[dict[str, Any]] = []
    for code in TRACKED_LEAGUES:
        competition = by_code.get(code)
        if competition is None:
            leagues.append(
                {
                    "code": code,
                    "name": code,
                    "season_label": None,
                    "finished": 0,
                    "upcoming": 0,
                    "last_sync_at": None,
                    "last_status": None,
                }
            )
            continue
        season = db.scalar(
            select(Season).where(
                Season.competition_id == competition.id,
                Season.is_current.is_(True),
            )
        )
        finished = 0
        upcoming = 0
        if season is not None:
            finished = db.scalar(
                select(func.count())
                .select_from(Match)
                .where(
                    Match.season_id == season.id,
                    Match.status == MatchStatus.TERMINE,
                )
            ) or 0
            upcoming = db.scalar(
                select(func.count())
                .select_from(Match)
                .where(
                    Match.season_id == season.id,
                    Match.status == MatchStatus.PROGRAMME,
                )
            ) or 0
        last = last_by_code.get(code)
        leagues.append(
            {
                "code": code,
                "name": competition.name,
                "season_label": season.label if season else None,
                "finished": int(finished),
                "upcoming": int(upcoming),
                "last_sync_at": last.applied_at if last else None,
                "last_status": last.status if last else None,
            }
        )

    matches_total = db.scalar(select(func.count()).select_from(Match)) or 0
    stats_rows = db.scalar(select(func.count()).select_from(TeamMatchStats)) or 0
    xg_rows = db.scalar(
        select(func.count())
        .select_from(TeamMatchStats)
        .where(TeamMatchStats.expected_goals.is_not(None))
    ) or 0
    teams_total = db.scalar(
        select(func.count()).select_from(Team).where(Team.external_id.is_not(None))
    ) or 0
    return {
        "provider": PROVIDER,
        "configured": bool(settings.bigballsdata_key),
        "season": settings.bigballsdata_season,
        "quota": {
            "used": info.used,
            "remaining": info.remaining,
            "limit": info.limit,
            "reset_at": info.reset_at,
        },
        "totals": {
            "matches": int(matches_total),
            "teams": int(teams_total),
            "stats_rows": int(stats_rows),
            "xg_rows": int(xg_rows),
        },
        "leagues": leagues,
        "runs": recent[:20],
    }
