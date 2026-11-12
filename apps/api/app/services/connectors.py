"""Orchestration des connecteurs : liens, aperçus, application, quotas."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.connectors.base import (
    ConnectorError,
    MissingKeyError,
    PreviewCounts,
    ProviderNotCoveredError,
)
from app.connectors.bigballsdata.client import BigBallsDataClient
from app.connectors.bigballsdata.importer import match_entry as bbd_match_entry
from app.connectors.bigballsdata.importer import stats_entry as bbd_stats_entry
from app.connectors.bigballsdata.mapping import map_league, map_match, map_statistics
from app.connectors.football_data.client import MIN_INTERVAL_SECONDS, FootballDataClient
from app.connectors.football_data.importer import match_entry as fd_match_entry
from app.connectors.football_data.mapping import map_match as fd_map_match
from app.connectors.football_data_uk import importer as csv_importer
from app.connectors.football_data_uk.client import FootballDataUkClient
from app.connectors.football_data_uk.mapping import discover_divisions, division_label
from app.connectors.http import HttpClient
from app.connectors.import_common import (
    apply_matches,
    apply_odds,
    apply_stats,
    as_utc,
    get_ref,
    get_ref_for_entity,
    link_ref,
    plan_matches,
    plan_odds,
    plan_stats,
)
from app.connectors.matching import kickoff_close, same_team_relaxed
from app.connectors.quota import (
    apply_headers,
    consume,
    ensure_budget,
    get_usage,
    snapshot,
)
from app.connectors.the_odds_api.client import TheOddsApiClient
from app.connectors.the_odds_api.importer import odds_entry
from app.connectors.the_odds_api.mapping import map_event_odds, map_events
from app.core.config import settings
from app.models.connector import (
    ConnectorLink,
    RefEntity,
    SyncOperation,
    SyncRun,
    SyncStatus,
)
from app.models.match import Match, MatchStatus, TeamMatchStats
from app.models.reference import Competition, Season, Team
from app.schemas.connector import (
    ConnectorLinkCreate,
    ConnectorLinkRead,
    ConnectorLinkUpdate,
    ProviderQuotaRead,
    ProviderStatusRead,
    ProviderUsageRead,
)

logger = logging.getLogger("odds_analyst.connectors")

PROVIDERS = ("bigballsdata", "the_odds_api", "football_data", "football_data_uk")

PROVIDER_LABELS = {
    "bigballsdata": "BigBallsData",
    "the_odds_api": "The Odds API (cotes 1xBet)",
    "football_data": "football-data.org",
    "football_data_uk": "football-data.co.uk (CSV)",
}

PROVIDER_ROLES = {
    "bigballsdata": "Calendrier, résultats et statistiques — source primaire.",
    "the_odds_api": "Cotes 1xBet agrégées — source primaire des marchés.",
    "football_data": "Repli calendrier et résultats — aucune cote, aucune statistique.",
    "football_data_uk": (
        "Résultats et statistiques (xG, tirs, corners, cartons) — fichier public, "
        "sans clé, sans quota."
    ),
}

PROVIDER_DOCS = {
    "bigballsdata": "https://bigballsdata.com/docs",
    "the_odds_api": "https://the-odds-api.com/liveapi/guides/v4/",
    "football_data": "https://docs.football-data.org/general/v4/index.html",
    "football_data_uk": "https://www.football-data.co.uk/data.php",
}

_LEAGUE_CACHE: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}
_LEAGUE_CACHE_TTL = timedelta(hours=24)

# Seules les rencontres programmées dans cette fenêtre sont importées. Les
# rencontres déjà jouées restent toujours importées : elles nourrissent le
# modèle statistique.
FIXTURE_WINDOW_DAYS = 10


def _entry_kickoff(entry: dict[str, Any]) -> datetime | None:
    value = entry.get("kickoff_at")
    if value is None:
        return None
    if isinstance(value, datetime):
        return as_utc(value)
    try:
        return as_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


def _within_fixture_window(
    entries: list[dict[str, Any]], *, now: datetime | None = None
) -> tuple[list[dict[str, Any]], int, datetime]:
    """Écarte les rencontres programmées au-delà de la fenêtre.

    Les rencontres dont le statut n'est pas « programme » (résultats, annulées)
    sont conservées sans limite de date : l'historique reste complet.
    """
    horizon = as_utc(now or datetime.now(UTC)) + timedelta(days=FIXTURE_WINDOW_DAYS)
    kept: list[dict[str, Any]] = []
    excluded = 0
    for entry in entries:
        if entry.get("status") == "programme":
            kickoff = _entry_kickoff(entry)
            if kickoff is not None and kickoff > horizon:
                excluded += 1
                continue
        kept.append(entry)
    return kept, excluded, horizon


def _quota_read(info: Any) -> ProviderQuotaRead:
    return ProviderQuotaRead(
        used=info.used,
        remaining=info.remaining,
        limit=info.limit,
        reset_at=info.reset_at,
    )


def _quota_info(db: Session, provider: str) -> Any:
    return snapshot(db, provider)


def client_for(provider: str, *, transport: Any = None) -> Any:
    """Construit le client du fournisseur, clé lue uniquement dans `.env`."""
    if provider == "bigballsdata":
        key = settings.bigballsdata_key
        if not key:
            raise MissingKeyError(
                "Clé BigBallsData absente. Renseignez BIGBALLSDATA_KEY dans .env "
                "puis redémarrez l'API."
            )
        http = HttpClient(
            timeout=settings.connector_timeout_seconds,
            max_retries=settings.connector_max_retries,
            min_interval=1.5,
            transport=transport,
        )
        return BigBallsDataClient(
            api_key=key, base_url=settings.bigballsdata_base_url, http=http
        )
    if provider == "the_odds_api":
        key = settings.the_odds_api_key
        if not key:
            raise MissingKeyError(
                "Clé The Odds API absente. Renseignez THE_ODDS_API_KEY dans .env "
                "puis redémarrez l'API."
            )
        http = HttpClient(
            timeout=settings.connector_timeout_seconds,
            max_retries=settings.connector_max_retries,
            transport=transport,
        )
        return TheOddsApiClient(
            api_key=key, base_url=settings.the_odds_api_base_url, http=http
        )
    if provider == "football_data":
        key = settings.football_data_key
        if not key:
            raise MissingKeyError(
                "Clé football-data.org absente. Renseignez FOOTBALL_DATA_KEY dans .env "
                "puis redémarrez l'API."
            )
        http = HttpClient(
            timeout=settings.connector_timeout_seconds,
            max_retries=settings.connector_max_retries,
            min_interval=MIN_INTERVAL_SECONDS,
            transport=transport,
        )
        return FootballDataClient(
            api_key=key, base_url=settings.football_data_base_url, http=http
        )
    if provider == "football_data_uk":
        http = HttpClient(
            timeout=settings.connector_timeout_seconds,
            max_retries=settings.connector_max_retries,
            transport=transport,
        )
        return FootballDataUkClient(
            base_url=settings.football_data_uk_base_url, http=http
        )
    raise ConnectorError("Fournisseur de données inconnu.", status_code=422)


# ---------------------------------------------------------------------------
# État et liens
# ---------------------------------------------------------------------------


def provider_statuses(db: Session) -> list[ProviderStatusRead]:
    statuses: list[ProviderStatusRead] = []
    for provider in PROVIDERS:
        configured = bool(
            {
                "bigballsdata": settings.bigballsdata_key,
                "the_odds_api": settings.the_odds_api_key,
                "football_data": settings.football_data_key,
                "football_data_uk": True,
            }[provider]
        )
        last_run = db.scalar(
            select(SyncRun)
            .where(SyncRun.provider == provider, SyncRun.status == SyncStatus.APPLIED.value)
            .order_by(SyncRun.applied_at.desc())
            .limit(1)
        )
        statuses.append(
            ProviderStatusRead(
                provider=provider,
                label=PROVIDER_LABELS[provider],
                configured=configured,
                role=PROVIDER_ROLES[provider],
                quota=_quota_read(_quota_info(db, provider)),
                last_sync_at=last_run.applied_at if last_run else None,
                documentation_url=PROVIDER_DOCS[provider],
            )
        )
    return statuses


def link_to_read(db: Session, link: ConnectorLink) -> ConnectorLinkRead:
    competition = db.get(Competition, link.competition_id)
    season = db.get(Season, link.season_id)
    data = ConnectorLinkRead.model_validate(link)
    return data.model_copy(
        update={
            "competition_name": competition.name if competition else None,
            "season_label": season.label if season else None,
        }
    )


def list_links(db: Session) -> list[ConnectorLinkRead]:
    links = db.scalars(select(ConnectorLink).order_by(ConnectorLink.created_at)).all()
    return [link_to_read(db, link) for link in links]


def create_link(db: Session, payload: ConnectorLinkCreate) -> ConnectorLinkRead:
    if db.get(Competition, payload.competition_id) is None:
        raise LookupError("Compétition interne introuvable.")
    if db.get(Season, payload.season_id) is None:
        raise LookupError("Saison interne introuvable.")
    link = ConnectorLink(
        provider=payload.provider,
        competition_id=payload.competition_id,
        season_id=payload.season_id,
        external_league_id=payload.external_league_id,
        external_season=payload.external_season,
        is_enabled=payload.is_enabled,
    )
    db.add(link)
    db.flush()
    return link_to_read(db, link)


def get_link(db: Session, link_id: UUID) -> ConnectorLink:
    link = db.get(ConnectorLink, link_id)
    if link is None:
        raise LookupError("Lien de connecteur introuvable.")
    return link


def update_link(
    db: Session, link: ConnectorLink, payload: ConnectorLinkUpdate
) -> ConnectorLinkRead:
    link.is_enabled = payload.is_enabled
    db.flush()
    return link_to_read(db, link)


def delete_link(db: Session, link: ConnectorLink) -> None:
    """Supprime le lien ; les données déjà importées restent en base."""
    db.delete(link)
    db.flush()


def provider_usage(db: Session) -> list[ProviderUsageRead]:
    rows: list[ProviderUsageRead] = []
    for provider in PROVIDERS:
        info = snapshot(db, provider)
        if info.limit is None:
            rows.append(
                ProviderUsageRead(
                    provider=provider,
                    period_kind="day",
                    period_start=datetime.now(UTC).date().isoformat(),
                    used=0,
                    limit=None,
                    remaining=None,
                    reset_at=None,
                )
            )
            continue
        usage = get_usage(db, provider)
        rows.append(
            ProviderUsageRead(
                provider=provider,
                period_kind=usage.period_kind,
                period_start=usage.period_start.isoformat(),
                used=info.used,
                limit=info.limit,
                remaining=info.remaining,
                reset_at=info.reset_at,
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Découverte des compétitions
# ---------------------------------------------------------------------------


def discover_bigballs_leagues(db: Session, search: str | None = None) -> list[dict[str, Any]]:
    cached = _LEAGUE_CACHE.get("bigballsdata")
    if cached and cached[0] > datetime.now(UTC) - _LEAGUE_CACHE_TTL:
        leagues = cached[1]
    else:
        client = client_for("bigballsdata")
        try:
            ensure_budget(db, "bigballsdata", 1)
            raw = client.list_leagues()
            consume(db, "bigballsdata", 1)
            apply_headers(db, "bigballsdata", {})
            leagues = [map_league(item) for item in raw]
            _LEAGUE_CACHE["bigballsdata"] = (datetime.now(UTC), leagues)
        finally:
            client.close()
    if search:
        needle = search.strip().lower()
        leagues = [item for item in leagues if needle in str(item["name"]).lower()]
    return leagues


def discover_csv_divisions(search: str | None = None) -> list[dict[str, Any]]:
    """Catalogue statique des divisions football-data.co.uk (pas d'API)."""
    items: list[dict[str, Any]] = [dict(item) for item in discover_divisions()]
    if search:
        needle = search.strip().lower()
        items = [
            item
            for item in items
            if needle in str(item["name"]).lower()
            or needle in str(item["external_id"]).lower()
        ]
    return items


def discover_competitions(db: Session, provider: str) -> list[dict[str, Any]]:
    if provider == "bigballsdata":
        return discover_bigballs_leagues(db)
    if provider == "the_odds_api":
        client = client_for("the_odds_api")
        try:
            sports = client.list_sports()
        finally:
            client.close()
        return [
            {"external_id": str(item.get("key")), "name": str(item.get("title")), "country": None}
            for item in sports
            if str(item.get("group", "")).lower() == "soccer"
        ]
    if provider == "football_data":
        client = client_for("football_data")
        try:
            ensure_budget(db, "football_data", 1)
            competitions = client.list_competitions()
            consume(db, "football_data", 1)
        finally:
            client.close()
        return [
            {
                "external_id": str(item.get("code")),
                "name": str(item.get("name")),
                "country": str(item.get("area", {}).get("name"))
                if isinstance(item.get("area"), dict)
                else None,
            }
            for item in competitions
        ]
    raise ConnectorError("Fournisseur de données inconnu.", status_code=422)


# ---------------------------------------------------------------------------
# Aperçus stockés
# ---------------------------------------------------------------------------


def _counts_dict(counts: PreviewCounts) -> dict[str, int]:
    return counts.as_dict()


def _store_run(
    db: Session,
    *,
    provider: str,
    operation: str,
    link: ConnectorLink,
    payload: dict[str, Any],
    counts: PreviewCounts,
    params: dict[str, Any] | None = None,
    requests_used: int = 0,
    credits_used: int = 0,
    warnings: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> SyncRun:
    info = snapshot(db, provider)
    summary = {
        "counts": _counts_dict(counts),
        "warnings": warnings or [],
        **(extra or {}),
    }
    now = datetime.now(UTC)
    run = SyncRun(
        provider=provider,
        operation=operation,
        status=SyncStatus.PREVIEW.value,
        link_id=link.id,
        params=params or {},
        payload=payload,
        summary=summary,
        requests_used=requests_used,
        credits_used=credits_used,
        quota_remaining=info.remaining,
        expires_at=now + timedelta(seconds=settings.connector_preview_ttl_seconds),
    )
    db.add(run)
    db.flush()
    return run


def preview_fixtures(db: Session, link: ConnectorLink) -> SyncRun:
    if not link.is_enabled:
        raise ProviderNotCoveredError("Ce lien est désactivé.")
    competition = db.get(Competition, link.competition_id)
    if competition is None:
        raise LookupError("Compétition interne introuvable.")

    requests_used = 0
    if link.provider == "bigballsdata":
        client = client_for("bigballsdata")
        try:
            raw_matches: list[dict[str, Any]] = []
            offset = 0
            for _ in range(10):
                ensure_budget(db, "bigballsdata", 1)
                page = client.list_matches(
                    league=link.external_league_id,
                    season=link.external_season,
                    offset=offset,
                )
                consume(db, "bigballsdata", 1)
                requests_used += 1
                raw_matches.extend(page)
                if len(page) < 100:
                    break
                offset += 100
            apply_headers(db, "bigballsdata", {})
        finally:
            client.close()
        normalized = [
            map_match(
                raw,
                competition_external_id=link.external_league_id,
                season_label=link.external_season,
            )
            for raw in raw_matches
        ]
        entries = [bbd_match_entry(item, str(link.season_id)) for item in normalized]
    elif link.provider == "football_data":
        client = client_for("football_data")
        try:
            ensure_budget(db, "football_data", 1)
            raw_matches = client.list_matches(link.external_league_id, link.external_season)
            consume(db, "football_data", 1)
            requests_used += 1
        finally:
            client.close()
        normalized = [fd_map_match(raw) for raw in raw_matches]
        entries = [fd_match_entry(item, str(link.season_id)) for item in normalized]
    else:
        raise ProviderNotCoveredError(
            "The Odds API ne fournit que des cotes, pas de calendrier."
        )

    received = len(entries)
    entries, excluded, horizon = _within_fixture_window(entries)

    plan, counts = plan_matches(
        db,
        provider=link.provider,
        sport_id=competition.sport_id,
        season_id=link.season_id,
        matches=entries,
    )
    plan["plan_kind"] = SyncOperation.FIXTURES.value
    counts.received = received
    warnings: list[str] = []
    if excluded:
        warnings.append(
            f"{excluded} rencontre(s) programmée(s) au-delà du "
            f"{horizon.strftime('%d/%m/%Y')} ignorée(s) : seules les rencontres "
            f"des {FIXTURE_WINDOW_DAYS} prochains jours sont importées."
        )
    unknown = [
        item["raw_status"]
        for item in entries
        if item.get("raw_status")
        and item["status"] == "programme"
        and item["raw_status"] not in {"scheduled"}
    ]
    if unknown:
        warnings.append(
            "Statut fournisseur inconnu traité comme « programme » : "
            + ", ".join(sorted({str(value) for value in unknown}))
        )
    return _store_run(
        db,
        provider=link.provider,
        operation=SyncOperation.FIXTURES.value,
        link=link,
        payload=plan,
        counts=counts,
        requests_used=requests_used,
        warnings=warnings,
        extra={
            "teams_to_create": plan.get("teams", []),
            "conflicts": [
                conflict
                for item in plan.get("matches", [])
                for conflict in item.get("conflicts", [])
            ],
        },
    )


def preview_csv(db: Session, link: ConnectorLink) -> SyncRun:
    """Télécharge le fichier CSV et prépare résultats et statistiques."""
    if link.provider != "football_data_uk":
        raise ProviderNotCoveredError(
            "Cette opération concerne uniquement football-data.co.uk."
        )
    if not link.is_enabled:
        raise ProviderNotCoveredError("Ce lien est désactivé.")
    competition = db.get(Competition, link.competition_id)
    if competition is None:
        raise LookupError("Compétition interne introuvable.")

    client = client_for("football_data_uk")
    try:
        rows = client.fetch_rows(
            division=link.external_league_id, season=link.external_season
        )
    finally:
        client.close()

    plan, counts, skipped = csv_importer.plan_import(
        db,
        provider="football_data_uk",
        season_id=link.season_id,
        sport_id=competition.sport_id,
        rows=rows,
    )
    plan["plan_kind"] = SyncOperation.RESULTS_STATS.value
    plan["division"] = division_label(link.external_league_id)

    warnings: list[str] = []
    if not rows:
        warnings.append("Aucune rencontre jouée dans ce fichier pour l'instant.")
    manquantes = sum(
        1 for item in skipped if str(item["reason"]).startswith("Rencontre")
    )
    if manquantes:
        warnings.append(
            f"{manquantes} rencontre(s) du fichier sont absentes du calendrier interne : "
            "importez d'abord le calendrier, puis relancez cet aperçu."
        )
    inconnues = sum(1 for item in skipped if str(item["reason"]).startswith("Équipe"))
    if inconnues:
        warnings.append(
            f"{inconnues} rencontre(s) ignorée(s) : équipe(s) non reconnue(s). "
            "Associez-les ci-dessous, puis relancez l'aperçu."
        )

    return _store_run(
        db,
        provider="football_data_uk",
        operation=SyncOperation.RESULTS_STATS.value,
        link=link,
        payload=plan,
        counts=counts,
        requests_used=1,
        warnings=warnings,
        extra={
            "skipped": skipped,
            "division": plan["division"],
            "source": "fichier CSV public",
        },
    )


def apply_preview(db: Session, run: SyncRun) -> PreviewCounts:
    if run.status != SyncStatus.PREVIEW.value:
        raise ConnectorError(
            "Cet aperçu a déjà été appliqué ou n'est plus valide.", status_code=409
        )
    if run.expires_at is not None and as_utc(run.expires_at) < datetime.now(UTC):
        run.status = SyncStatus.EXPIRED.value
        db.flush()
        raise ConnectorError(
            "Cet aperçu a expiré. Relancez-le pour actualiser les données.", status_code=410
        )
    plan = run.payload or {}
    kind = plan.get("plan_kind")
    if kind == SyncOperation.FIXTURES.value:
        counts = apply_matches(db, plan)
        link = db.get(ConnectorLink, run.link_id) if run.link_id else None
        if link is not None:
            link.last_fixtures_sync_at = datetime.now(UTC)
    elif kind == SyncOperation.RESULTS_STATS.value:
        counts = csv_importer.apply_import(db, plan)
        link = db.get(ConnectorLink, run.link_id) if run.link_id else None
        if link is not None:
            link.last_stats_sync_at = datetime.now(UTC)
    elif kind in {SyncOperation.ODDS.value, SyncOperation.ODDS_EXTENDED.value}:
        counts = apply_odds(db, plan)
        link = db.get(ConnectorLink, run.link_id) if run.link_id else None
        if link is not None:
            link.last_odds_sync_at = datetime.now(UTC)
    else:
        raise ConnectorError("Type d'aperçu inconnu.", status_code=422)

    run.status = SyncStatus.APPLIED.value
    run.applied_at = datetime.now(UTC)
    run.summary = {**(run.summary or {}), "counts": _counts_dict(counts)}
    db.flush()
    return counts


def preview_odds(db: Session, link: ConnectorLink, *, extended: bool = False) -> SyncRun:
    if link.provider != "the_odds_api":
        raise ProviderNotCoveredError("Les cotes proviennent uniquement de The Odds API.")
    if not link.is_enabled:
        raise ProviderNotCoveredError("Ce lien est désactivé.")

    client = client_for("the_odds_api")
    try:
        ensure_budget(db, "the_odds_api", 2)
        raw = client.competition_odds(link.external_league_id, markets="h2h,totals")
        consume(db, "the_odds_api", 2)
    finally:
        client.close()

    mapped = map_events(raw, allowed={"h2h", "totals"})
    warnings: list[str] = []
    if not mapped:
        warnings.append(
            "1xBet indisponible pour cette compétition : aucune cote importée, "
            "aucune substitution de bookmaker."
        )

    items: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for event in mapped:
        match = _resolve_event_match(
            db, link, event.event_id, event.home_team, event.away_team, event.commence_time
        )
        if match is None:
            unmatched.append(
                {
                    "event_id": event.event_id,
                    "label": f"{event.home_team} — {event.away_team}",
                    "kickoff_utc": event.commence_time.isoformat(),
                }
            )
            continue
        items.append(odds_entry(event, str(match.id)))

    plan, counts = plan_odds(db, provider="the_odds_api", items=items)
    plan["plan_kind"] = SyncOperation.ODDS.value
    counts.ignored += len(unmatched)
    return _store_run(
        db,
        provider="the_odds_api",
        operation=SyncOperation.ODDS.value,
        link=link,
        payload=plan,
        counts=counts,
        credits_used=2,
        warnings=warnings,
        extra={"bookmaker": "1xBet", "unmatched": unmatched},
    )


def preview_extended_odds(
    db: Session, link: ConnectorLink, match_ids: list[UUID]
) -> SyncRun:
    if link.provider != "the_odds_api":
        raise ProviderNotCoveredError("Les cotes proviennent uniquement de The Odds API.")
    if not match_ids:
        raise ConnectorError("Sélectionnez au moins une rencontre.", status_code=422)
    if len(match_ids) > settings.connector_max_extended_events:
        raise ConnectorError(
            f"Un lot est limité à {settings.connector_max_extended_events} rencontres.",
            status_code=422,
        )

    client = client_for("the_odds_api")
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    credits = 0
    try:
        for match_id in match_ids:
            ref = get_ref_for_entity(db, "the_odds_api", RefEntity.MATCH.value, match_id)
            if ref is None:
                warnings.append(f"Rencontre {match_id} sans événement associé.")
                continue
            ensure_budget(db, "the_odds_api", 2)
            raw = client.event_odds(
                link.external_league_id, ref.external_id, markets="double_chance,btts"
            )
            consume(db, "the_odds_api", 2)
            credits += 2
            mapped = map_event_odds(raw, allowed={"double_chance", "btts"})
            if mapped is None or not mapped.markets:
                warnings.append(
                    f"1xBet ne propose pas la double chance ou le BTTS pour l'événement "
                    f"{ref.external_id}."
                )
                continue
            items.append(odds_entry(mapped, str(match_id)))
    finally:
        client.close()

    plan, counts = plan_odds(db, provider="the_odds_api", items=items)
    plan["plan_kind"] = SyncOperation.ODDS_EXTENDED.value
    return _store_run(
        db,
        provider="the_odds_api",
        operation=SyncOperation.ODDS_EXTENDED.value,
        link=link,
        payload=plan,
        counts=counts,
        credits_used=credits,
        warnings=warnings,
        extra={"bookmaker": "1xBet", "markets": ["double_chance", "btts"]},
    )


# ---------------------------------------------------------------------------
# Appariement des événements
# ---------------------------------------------------------------------------


def _season_matches(db: Session, season_id: UUID) -> list[Match]:
    return list(
        db.scalars(
            select(Match)
            .where(Match.season_id == season_id)
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
        ).all()
    )


def _resolve_event_match(
    db: Session,
    link: ConnectorLink,
    event_id: str,
    home_team: str,
    away_team: str,
    commence_time: datetime,
) -> Match | None:
    ref = get_ref(db, "the_odds_api", RefEntity.MATCH.value, event_id)
    if ref is not None:
        return db.get(Match, ref.entity_id)

    candidates = _season_matches(db, link.season_id)
    matches = [
        candidate
        for candidate in candidates
        if kickoff_close(as_utc(candidate.kickoff_at), commence_time)
        and same_team_relaxed(
            home_team,
            None,
            candidate.home_team.name,
            candidate.home_team.short_name,
        )
        and same_team_relaxed(
            away_team,
            None,
            candidate.away_team.name,
            candidate.away_team.short_name,
        )
    ]
    if len(matches) != 1:
        return None
    link_ref(db, "the_odds_api", RefEntity.MATCH, matches[0].id, event_id)
    return matches[0]


def list_odds_events(
    db: Session, link: ConnectorLink
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if link.provider != "the_odds_api":
        raise ProviderNotCoveredError("Les événements proviennent uniquement de The Odds API.")
    client = client_for("the_odds_api")
    try:
        events = client.list_events(link.external_league_id)
    finally:
        client.close()
    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for raw in events:
        event_id = str(raw.get("id") or "")
        home = str(raw.get("home_team") or "")
        away = str(raw.get("away_team") or "")
        try:
            commence = as_utc(
                datetime.fromisoformat(str(raw.get("commence_time")).replace("Z", "+00:00"))
            )
        except ValueError:
            continue
        match = _resolve_event_match(db, link, event_id, home, away, commence)
        item = {
            "event_id": event_id,
            "home_team": home,
            "away_team": away,
            "commence_time": commence,
            "match_id": match.id if match else None,
            "match_label": (
                f"{match.home_team.name} — {match.away_team.name}" if match else None
            ),
        }
        (matched if match else unmatched).append(item)
    return matched, unmatched


def link_event(db: Session, link: ConnectorLink, event_id: str, match_id: UUID) -> None:
    match = db.get(Match, match_id)
    if match is None:
        raise LookupError("Rencontre interne introuvable.")
    link_ref(db, "the_odds_api", RefEntity.MATCH, match.id, event_id)


def link_csv_team(db: Session, link: ConnectorLink, external_id: str, team_id: UUID) -> None:
    """Associe durablement un nom d'équipe du CSV à une équipe interne."""
    if link.provider != "football_data_uk":
        raise ProviderNotCoveredError(
            "Cette association concerne uniquement football-data.co.uk."
        )
    team = db.get(Team, team_id)
    if team is None:
        raise LookupError("Équipe interne introuvable.")
    link_ref(db, "football_data_uk", RefEntity.TEAM, team.id, external_id.strip())


# ---------------------------------------------------------------------------
# Statistiques par lots
# ---------------------------------------------------------------------------


def stats_candidates(db: Session, link: ConnectorLink) -> list[Match]:
    """Rencontres terminées du lien, sans statistiques, hors source de cotes."""
    with_stats = select(TeamMatchStats.match_id).where(TeamMatchStats.match_id == Match.id)
    return list(
        db.scalars(
            select(Match)
            .where(
                Match.season_id == link.season_id,
                Match.status == MatchStatus.TERMINE,
                ~with_stats.exists(),
            )
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .order_by(Match.kickoff_at)
        ).all()
    )


def apply_stats_batch(
    db: Session, link: ConnectorLink, match_ids: list[UUID]
) -> dict[str, Any]:
    if link.provider != "bigballsdata":
        raise ProviderNotCoveredError(
            "Les statistiques d'équipe proviennent uniquement de BigBallsData."
        )
    if not match_ids:
        raise ConnectorError("Sélectionnez au moins une rencontre.", status_code=422)
    if len(match_ids) > settings.connector_max_stats_batch:
        raise ConnectorError(
            f"Un lot est limité à {settings.connector_max_stats_batch} rencontres.",
            status_code=422,
        )

    results: list[dict[str, Any]] = []
    created = 0
    conflicts = 0
    ignored = 0
    client = client_for("bigballsdata")
    try:
        for match_id in match_ids:
            match_uuid = UUID(str(match_id))
            match = db.get(Match, match_uuid)
            if match is None:
                results.append(
                    {
                        "match_id": match_uuid,
                        "status": "ignored",
                        "message": "Rencontre introuvable.",
                    }
                )
                ignored += 1
                continue
            ref = get_ref_for_entity(db, "bigballsdata", RefEntity.MATCH.value, match_uuid)
            if ref is None:
                results.append(
                    {
                        "match_id": match_uuid,
                        "status": "ignored",
                        "message": "Rencontre non associée à BigBallsData.",
                    }
                )
                ignored += 1
                continue
            ensure_budget(db, "bigballsdata", 1)
            data = client.get_statistics(ref.external_id)
            consume(db, "bigballsdata", 1)
            home_ref = get_ref_for_entity(
                db, "bigballsdata", RefEntity.TEAM.value, match.home_team_id
            )
            away_ref = get_ref_for_entity(
                db, "bigballsdata", RefEntity.TEAM.value, match.away_team_id
            )
            lines = map_statistics(
                data,
                match_external_id=ref.external_id,
                home_id=home_ref.external_id if home_ref else str(match.home_team_id),
                away_id=away_ref.external_id if away_ref else str(match.away_team_id),
            )
            if not lines:
                results.append(
                    {
                        "match_id": match_id,
                        "status": "ignored",
                        "message": "Statistiques indisponibles chez le fournisseur.",
                    }
                )
                ignored += 1
                continue
            team_ids = {}
            if home_ref:
                team_ids[home_ref.external_id] = str(match.home_team_id)
            if away_ref:
                team_ids[away_ref.external_id] = str(match.away_team_id)
            entry = bbd_stats_entry(
                str(match.id),
                lines,
                team_ids,
                (match.home_score, match.away_score),
            )
            plan, preview = plan_stats(db, provider="bigballsdata", items=[entry])
            if preview.conflicts:
                conflicts += 1
                results.append(
                    {
                        "match_id": match_id,
                        "status": "conflict",
                        "message": "Des statistiques existent déjà et sont conservées.",
                    }
                )
                continue
            counts = apply_stats(db, plan)
            created += counts.created
            results.append({"match_id": match_id, "status": "created", "message": None})
            db.commit()
    finally:
        client.close()
    return {
        "results": results,
        "created": created,
        "conflicts": conflicts,
        "ignored": ignored,
    }


def preview_stats(db: Session, link: ConnectorLink) -> dict[str, Any]:
    candidates = stats_candidates(db, link)
    info = snapshot(db, link.provider)
    return {
        "provider": link.provider,
        "candidates": candidates,
        "cost": min(len(candidates), settings.connector_max_stats_batch),
        "budget_remaining": info.remaining or 0,
    }


# ---------------------------------------------------------------------------
# Journal et reprise
# ---------------------------------------------------------------------------


def list_runs(db: Session, limit: int = 20) -> list[SyncRun]:
    return list(
        db.scalars(select(SyncRun).order_by(SyncRun.created_at.desc()).limit(limit)).all()
    )


def get_run(db: Session, run_id: UUID) -> SyncRun:
    run = db.get(SyncRun, run_id)
    if run is None:
        raise LookupError("Synchronisation introuvable.")
    return run


def recover_interrupted(db: Session) -> int:
    """Marque comme interrompues les synchronisations restées en cours."""
    runs = db.scalars(
        select(SyncRun).where(SyncRun.status == "running")
    ).all()
    for run in runs:
        run.status = SyncStatus.INTERRUPTED.value
    db.flush()
    return len(runs)


def purge_expired(db: Session) -> int:
    """Supprime les aperçus expirés depuis plus de 7 jours."""
    threshold = datetime.now(UTC) - timedelta(days=7)
    runs = db.scalars(
        select(SyncRun).where(
            SyncRun.status.in_([SyncStatus.EXPIRED.value, SyncStatus.PREVIEW.value]),
            SyncRun.expires_at.is_not(None),
            SyncRun.expires_at < threshold,
        )
    ).all()
    for run in runs:
        db.delete(run)
    db.flush()
    return len(runs)
