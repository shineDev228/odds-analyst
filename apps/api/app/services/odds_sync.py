"""Import des cotes 1xBet des rencontres à venir (The Odds API).

Trois principes :

1. **Mesurer avant de payer.** L'aperçu interroge `/events`, gratuit, et
   n'écrit rien. La passe payante n'est lancée qu'ensuite.
2. **Ne jamais deviner.** L'appariement est celui d'`odds_matching` : clé
   composite, seuil et marge. En cas de doute, aucun lien n'est créé.
3. **Ne rien écraser.** Un marché saisi à la main (`is_custom`) est ignoré et
   compté ; un relevé identique au précédent n'est pas réécrit.

Le fournisseur facture un crédit par marché et par région. L'appel compétition
(1X2 + totaux) coûte 2 crédits ; les marchés étendus (double chance + BTTS)
n'existent que par événement et coûtent 2 crédits chacun. Ils sont bornés à la
fenêtre de 72 heures et à 30 rencontres par passe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.connectors.base import (
    BudgetExceededError,
    ConnectorError,
    MissingKeyError,
    NormalizedEventOdds,
    ProviderRateLimitError,
)
from app.connectors.http import HttpClient
from app.connectors.odds_matching import Decision, EventRef, MatchCandidate, decide_event
from app.connectors.quota import apply_headers, consume, ensure_budget, snapshot
from app.connectors.the_odds_api.client import TheOddsApiClient
from app.connectors.the_odds_api.mapping import (
    BOOKMAKER_LABEL,
    map_event_odds,
    parse_datetime,
)
from app.core.config import settings
from app.models.connector import SyncOperation, SyncRun, SyncStatus
from app.models.link import OddsEventLink
from app.models.market import Market, OddsSnapshot, Selection
from app.models.match import Match, MatchStatus
from app.models.reference import Competition, Season
from app.services.markets import as_utc, build_signature, resolve_template

PROVIDER = "the_odds_api"
SOURCE = "the_odds_api"
MARKETS_COMPETITION = "h2h,totals"
MARKETS_EXTENDED = "double_chance,btts"
COMPETITION_CREDITS = 2
EVENT_CREDITS = 2
EXTENDED_WINDOW_HOURS = 72
EXTENDED_MAX_EVENTS = 30
# Espacement minimal entre deux appels : le fournisseur reste sollicité sans
# rafale, comme pour BigBallsData.
MIN_INTERVAL_SECONDS = 0.5
# Fenêtre de recherche des rencontres candidates autour de l'événement.
CANDIDATE_PAST_HOURS = 2
CANDIDATE_FUTURE_DAYS = 30

SPORT_KEYS: dict[str, str] = {
    "ligue1": "soccer_france_ligue_one",
    "laliga": "soccer_spain_la_liga",
    "epl": "soccer_epl",
    "seriea": "soccer_italy_serie_a",
    "bundesliga": "soccer_germany_bundesliga",
    "ucl": "soccer_uefa_champs_league",
    "mls": "soccer_usa_mls",
}
TRACKED_LEAGUES = tuple(SPORT_KEYS)


@dataclass(slots=True)
class LeagueOddsReport:
    code: str
    name: str
    status: str = "applied"
    events: int = 0
    matched: int = 0
    ambiguous: int = 0
    unmatched: int = 0
    links_created: int = 0
    links_reused: int = 0
    links_deactivated: int = 0
    bookmaker_missing: int = 0
    markets_written: int = 0
    snapshots_written: int = 0
    manual_kept: int = 0
    extended_events: int = 0
    credits: int = 0
    requests: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "status": self.status,
            "events": self.events,
            "matched": self.matched,
            "ambiguous": self.ambiguous,
            "unmatched": self.unmatched,
            "links_created": self.links_created,
            "links_reused": self.links_reused,
            "links_deactivated": self.links_deactivated,
            "bookmaker_missing": self.bookmaker_missing,
            "markets_written": self.markets_written,
            "snapshots_written": self.snapshots_written,
            "manual_kept": self.manual_kept,
            "extended_events": self.extended_events,
            "credits": self.credits,
            "warnings": list(self.warnings),
            "error": self.error,
        }


@dataclass(slots=True)
class OddsReport:
    provider: str = PROVIDER
    status: str = "applied"
    credits_used: int = 0
    requests: int = 0
    quota_remaining: int | None = None
    error: str | None = None
    leagues: list[LeagueOddsReport] = field(default_factory=list)

    @property
    def totals(self) -> dict[str, int]:
        return {
            "events": sum(item.events for item in self.leagues),
            "matched": sum(item.matched for item in self.leagues),
            "ambiguous": sum(item.ambiguous for item in self.leagues),
            "unmatched": sum(item.unmatched for item in self.leagues),
            "links_created": sum(item.links_created for item in self.leagues),
            "links_reused": sum(item.links_reused for item in self.leagues),
            "links_deactivated": sum(item.links_deactivated for item in self.leagues),
            "bookmaker_missing": sum(item.bookmaker_missing for item in self.leagues),
            "markets_written": sum(item.markets_written for item in self.leagues),
            "snapshots_written": sum(item.snapshots_written for item in self.leagues),
            "manual_kept": sum(item.manual_kept for item in self.leagues),
            "extended_events": sum(item.extended_events for item in self.leagues),
            "credits": sum(item.credits for item in self.leagues),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "credits_used": self.credits_used,
            "requests": self.requests,
            "quota_remaining": self.quota_remaining,
            "error": self.error,
            "totals": self.totals,
            "leagues": [item.as_dict() for item in self.leagues],
        }


@dataclass(slots=True)
class PreviewEvent:
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "commence_at": self.commence_at,
            "decision": self.decision,
            "method": self.method,
            "confidence": self.confidence,
            "margin": self.margin,
            "match_id": self.match_id,
            "match_label": self.match_label,
        }


@dataclass(slots=True)
class PreviewLeague:
    code: str
    name: str
    status: str = "applied"
    events: int = 0
    matched: int = 0
    ambiguous: int = 0
    unmatched: int = 0
    credits: int = 0
    items: list[PreviewEvent] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "status": self.status,
            "events": self.events,
            "matched": self.matched,
            "ambiguous": self.ambiguous,
            "unmatched": self.unmatched,
            "credits": self.credits,
            "items": [item.as_dict() for item in self.items],
            "error": self.error,
        }


@dataclass(slots=True)
class PreviewReport:
    provider: str = PROVIDER
    status: str = "preview"
    credits_estimated: int = 0
    quota_remaining: int | None = None
    error: str | None = None
    leagues: list[PreviewLeague] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "credits_estimated": self.credits_estimated,
            "quota_remaining": self.quota_remaining,
            "error": self.error,
            "leagues": [item.as_dict() for item in self.leagues],
        }


@dataclass(slots=True)
class _PlannedEvent:
    event: EventRef
    decision: Decision
    match_id: UUID | None
    existing: bool = False


def make_client() -> TheOddsApiClient:
    """Construit le client à partir du `.env` ; la clé n'est jamais journalisée."""
    if not settings.the_odds_api_key:
        raise MissingKeyError(
            "Clé The Odds API absente. Renseignez THE_ODDS_API_KEY dans .env "
            "puis redémarrez l'API."
        )
    http = HttpClient(
        timeout=settings.connector_timeout_seconds,
        max_retries=settings.connector_max_retries,
        min_interval=MIN_INTERVAL_SECONDS,
    )
    return TheOddsApiClient(
        api_key=settings.the_odds_api_key,
        base_url=settings.the_odds_api_base_url,
        http=http,
    )


def _selected(leagues: list[str] | None) -> list[str]:
    return [code for code in (leagues or TRACKED_LEAGUES) if code in SPORT_KEYS]


def _candidates(db: Session, code: str, now: datetime) -> list[MatchCandidate]:
    """Rencontres à venir de la compétition, avec les noms du fournisseur de faits."""
    debut = now - timedelta(hours=CANDIDATE_PAST_HOURS)
    fin = now + timedelta(days=CANDIDATE_FUTURE_DAYS)
    rows = db.scalars(
        select(Match)
        .join(Season, Season.id == Match.season_id)
        .join(Competition, Competition.id == Season.competition_id)
        .where(
            Competition.code == code,
            Match.status == MatchStatus.PROGRAMME,
            Match.kickoff_at >= debut,
            Match.kickoff_at <= fin,
        )
        .options(selectinload(Match.home_team), selectinload(Match.away_team))
    ).all()
    return [
        MatchCandidate(
            match_id=row.id,
            home_name=row.home_team.name,
            away_name=row.away_team.name,
            kickoff_at=as_utc(row.kickoff_at),
        )
        for row in rows
    ]


def _event_refs(raw_events: list[dict[str, Any]]) -> list[EventRef]:
    refs: list[EventRef] = []
    for raw in raw_events:
        event_id = str(raw.get("id") or "")
        home = str(raw.get("home_team") or "")
        away = str(raw.get("away_team") or "")
        if not event_id or not home or not away:
            continue
        try:
            commence = parse_datetime(raw.get("commence_time"))
        except ValueError:
            continue
        refs.append(
            EventRef(
                event_id=event_id,
                home_name=home,
                away_name=away,
                commence_at=commence,
            )
        )
    return refs


def _link_index(db: Session, events: list[EventRef]) -> dict[str, OddsEventLink]:
    ids = [event.event_id for event in events]
    if not ids:
        return {}
    rows = db.scalars(
        select(OddsEventLink).where(
            OddsEventLink.provider == PROVIDER,
            OddsEventLink.event_id.in_(ids),
        )
    ).all()
    return {row.event_id: row for row in rows}


def _plan(
    db: Session,
    events: list[EventRef],
    candidates: list[MatchCandidate],
) -> list[_PlannedEvent]:
    """Décide du rattachement de chaque événement, sans rien écrire."""
    links = _link_index(db, events)
    plan: list[_PlannedEvent] = []
    for event in events:
        link = links.get(event.event_id)
        if link is not None:
            plan.append(
                _PlannedEvent(
                    event=event,
                    decision=Decision(
                        match_id=link.match_id,
                        method=link.method,
                        confidence=float(link.confidence or 0.0),
                        margin=float(link.margin or 0.0),
                        reason="matched",
                    ),
                    match_id=link.match_id,
                    existing=True,
                )
            )
            continue
        decision = decide_event(event, candidates)
        plan.append(
            _PlannedEvent(
                event=event,
                decision=decision,
                match_id=decision.match_id,
            )
        )
    return plan


def _count(plan: list[_PlannedEvent], item: LeagueOddsReport | PreviewLeague) -> None:
    item.events = len(plan)
    item.matched = sum(1 for entry in plan if entry.decision.reason == "matched")
    item.ambiguous = sum(1 for entry in plan if entry.decision.reason == "ambiguous")
    item.unmatched = sum(1 for entry in plan if entry.decision.reason == "unmatched")


def _competition_name(db: Session, code: str) -> str:
    name = db.scalar(select(Competition.name).where(Competition.code == code))
    return str(name or code)


def _extended_targets(plan: list[_PlannedEvent], now: datetime, limite: int) -> list[EventRef]:
    """Événements retenus pour les marchés étendus : proches, puis plafonnés."""
    horizon = now + timedelta(hours=EXTENDED_WINDOW_HOURS)
    retenus = [
        entry.event
        for entry in plan
        if entry.match_id is not None
        and now <= as_utc(entry.event.commence_at) <= horizon
    ]
    retenus.sort(key=lambda event: as_utc(event.commence_at))
    return retenus[: max(limite, 0)]


def _match_label(db: Session, match_id: UUID | None) -> str | None:
    if match_id is None:
        return None
    match = db.get(Match, match_id)
    if match is None:
        return None
    return f"{match.home_team.name} - {match.away_team.name}"


def preview(
    db: Session,
    *,
    leagues: list[str] | None = None,
    include_extended: bool = True,
    extended_limit: int = EXTENDED_MAX_EVENTS,
    now: datetime | None = None,
    client: Any | None = None,
) -> PreviewReport:
    """Relevé gratuit : décisions d'appariement et coût estimé, sans écriture."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    report = PreviewReport()
    selected = _selected(leagues)
    if not selected:
        report.status = "empty"
        return report

    limite = min(max(extended_limit, 0), EXTENDED_MAX_EVENTS)
    restant = limite
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

        for code in selected:
            league = PreviewLeague(code=code, name=_competition_name(db, code))
            try:
                raw_events = connector.list_events(SPORT_KEYS[code])
                events = _event_refs(raw_events)
                plan = _plan(db, events, _candidates(db, code, moment))
                _count(plan, league)
                extended = _extended_targets(plan, moment, restant) if include_extended else []
                restant = max(restant - len(extended), 0)
                league.credits = (
                    COMPETITION_CREDITS + len(extended) * EVENT_CREDITS
                    if events
                    else 0
                )
                if not events:
                    league.status = "empty"
                for entry in plan:
                    league.items.append(
                        PreviewEvent(
                            event_id=entry.event.event_id,
                            home_team=entry.event.home_name,
                            away_team=entry.event.away_name,
                            commence_at=entry.event.commence_at,
                            decision=entry.decision.reason,
                            method=entry.decision.method,
                            confidence=entry.decision.confidence,
                            margin=entry.decision.margin,
                            match_id=entry.match_id,
                            match_label=_match_label(db, entry.match_id),
                        )
                    )
            except (BudgetExceededError, ProviderRateLimitError) as exc:
                league.status = "failed"
                league.error = exc.message
                report.status = "partial"
            except ConnectorError as exc:
                league.status = "failed"
                league.error = exc.message
                report.status = "partial"
            report.leagues.append(league)

        report.credits_estimated = sum(item.credits for item in report.leagues)
        if all(item.status == "failed" for item in report.leagues):
            report.status = "failed"
        elif any(item.status == "failed" for item in report.leagues):
            report.status = "partial"
        elif all(item.status == "empty" for item in report.leagues):
            report.status = "empty"
        else:
            report.status = "preview"
    finally:
        if own_client and connector is not None:
            connector.close()

    report.quota_remaining = snapshot(db, PROVIDER, moment).remaining
    return report


def run(
    db: Session,
    *,
    leagues: list[str] | None = None,
    include_extended: bool = True,
    extended_limit: int = EXTENDED_MAX_EVENTS,
    now: datetime | None = None,
    client: Any | None = None,
) -> OddsReport:
    """Importe les cotes des rencontres à venir. Ne valide pas la transaction."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    report = OddsReport()
    selected = _selected(leagues)
    if not selected:
        report.status = "empty"
        return report

    limite = min(max(extended_limit, 0), EXTENDED_MAX_EVENTS)
    restant = limite
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

        stopped = False
        for code in selected:
            item = LeagueOddsReport(code=code, name=_competition_name(db, code))
            if stopped:
                item.status = "skipped"
                item.error = "Passe arrêtée : quota ou limitation atteinte."
                report.leagues.append(item)
                continue
            try:
                restant -= _run_league(
                    db,
                    connector,
                    item=item,
                    code=code,
                    moment=moment,
                    include_extended=include_extended,
                    extended_limit=restant,
                )
                restant = max(restant, 0)
            except (BudgetExceededError, ProviderRateLimitError) as exc:
                stopped = True
                item.status = "failed"
                item.error = exc.message
            except ConnectorError as exc:
                item.status = "failed"
                item.error = exc.message
            report.leagues.append(item)
            report.requests += item.requests

        if stopped:
            applied = any(item.status == "applied" for item in report.leagues)
            report.status = "partial" if applied else "failed"
        elif any(item.status == "partial" for item in report.leagues):
            report.status = "partial"
        elif any(item.status == "failed" for item in report.leagues):
            applied = any(item.status == "applied" for item in report.leagues)
            report.status = "partial" if applied else "failed"
        elif all(item.status == "empty" for item in report.leagues):
            report.status = "empty"
        else:
            report.status = "applied"
        report.credits_used = report.totals["credits"]
        _record_run(db, report, moment)
    finally:
        if own_client and connector is not None:
            connector.close()

    report.quota_remaining = snapshot(db, PROVIDER, moment).remaining
    return report


def _run_league(
    db: Session,
    client: Any,
    *,
    item: LeagueOddsReport,
    code: str,
    moment: datetime,
    include_extended: bool,
    extended_limit: int,
) -> int:
    """Importe une compétition ; renvoie le nombre d'appels étendus effectués."""
    raw_events = client.list_events(SPORT_KEYS[code])
    item.requests += 1
    events = _event_refs(raw_events)
    plan = _plan(db, events, _candidates(db, code, moment))
    _count(plan, item)

    # Les décisions sont enregistrées avant l'appel payant : un échec de cotes
    # ne fait pas perdre l'appariement, qui sera réutilisé à la passe suivante.
    matches: dict[str, UUID] = {}
    claimed: set[UUID] = set()
    for entry in plan:
        if entry.match_id is None:
            continue
        if entry.match_id in claimed:
            item.warnings.append(
                "Deux événements revendiquent la même rencontre : le premier est retenu."
            )
            continue
        claimed.add(entry.match_id)
        matches[entry.event.event_id] = entry.match_id
        if entry.existing:
            item.links_reused += 1
            _reactivate_link(db, entry, item)
        else:
            _create_link(db, entry, code=code, moment=moment, item=item)

    if item.ambiguous:
        item.warnings.append(
            f"{item.ambiguous} événement(s) ambigu(s) : aucun lien créé, aucune cote écrite."
        )
    if item.unmatched:
        item.warnings.append(
            f"{item.unmatched} événement(s) sans rencontre correspondante : ignoré(s)."
        )

    if not events:
        item.status = "empty"
        item.warnings.append("Aucun événement à venir chez le fournisseur.")
        return 0

    if not matches:
        # Rien n'est rattachable : payer des cotes qui ne seraient pas écrites
        # serait une dépense sans effet.
        item.status = "empty"
        item.warnings.append(
            "Aucune rencontre rattachée : aucun crédit dépensé pour les cotes."
        )
        return 0

    ensure_budget(db, PROVIDER, COMPETITION_CREDITS, now=moment)
    try:
        raw_odds = client.competition_odds(SPORT_KEYS[code], markets=MARKETS_COMPETITION)
    except BudgetExceededError:
        raise
    except ProviderRateLimitError:
        raise
    consume(db, PROVIDER, COMPETITION_CREDITS, now=moment)
    apply_headers(db, PROVIDER, client.last_headers or {}, now=moment)
    item.credits += COMPETITION_CREDITS
    item.requests += 1

    for raw in raw_odds:
        mapped = map_event_odds(raw, allowed={"h2h", "totals"})
        if mapped is None:
            item.bookmaker_missing += 1
            continue
        match_id = matches.get(mapped.event_id)
        if match_id is None:
            item.warnings.append(
                "Événement coté sans rencontre correspondante : ignoré."
            )
            continue
        match = db.get(Match, match_id)
        if match is None:
            continue
        _write_odds(db, match, mapped, item)

    if not include_extended or extended_limit <= 0:
        _append_warnings(item)
        return 0

    fetched = 0
    targets = _extended_targets(plan, moment, extended_limit)
    for event in targets:
        match_id = matches.get(event.event_id)
        if match_id is None:
            continue
        try:
            ensure_budget(db, PROVIDER, EVENT_CREDITS, now=moment)
            payload = client.event_odds(
                SPORT_KEYS[code], event.event_id, markets=MARKETS_EXTENDED
            )
        except (BudgetExceededError, ProviderRateLimitError) as exc:
            item.status = "partial"
            item.warnings.append(f"Marchés étendus arrêtés : {exc.message}")
            _append_warnings(item)
            return fetched
        except ConnectorError as exc:
            item.warnings.append(
                f"Marchés étendus indisponibles pour {event.home_name} - {event.away_name} : "
                f"{exc.message}"
            )
            continue
        fetched += 1
        consume(db, PROVIDER, EVENT_CREDITS, now=moment)
        apply_headers(db, PROVIDER, client.last_headers or {}, now=moment)
        item.credits += EVENT_CREDITS
        item.requests += 1
        mapped = map_event_odds(payload, allowed={"double_chance", "btts"})
        if mapped is None:
            item.bookmaker_missing += 1
            continue
        match = db.get(Match, match_id)
        if match is None:
            continue
        _write_odds(db, match, mapped, item)
        item.extended_events += 1

    _append_warnings(item)
    return fetched


def _append_warnings(item: LeagueOddsReport) -> None:
    """Ajoute les avertissements de fin de compétition, une seule fois."""
    if item.bookmaker_missing:
        item.warnings.append(
            f"{item.bookmaker_missing} événement(s) sans 1xBet : aucune cote inventée."
        )
    if item.manual_kept:
        item.warnings.append(
            f"{item.manual_kept} marché(s) saisi(s) à la main conservé(s) tel(s) quel(s)."
        )


def _create_link(
    db: Session,
    entry: _PlannedEvent,
    *,
    code: str,
    moment: datetime,
    item: LeagueOddsReport,
) -> None:
    assert entry.match_id is not None
    _deactivate_other_links(db, entry.match_id, item=item)
    # L'index « un seul lien actif par rencontre » impose de désactiver avant
    # d'insérer : on valide la désactivation séparément.
    db.flush()
    db.add(
        OddsEventLink(
            provider=PROVIDER,
            event_id=entry.event.event_id,
            match_id=entry.match_id,
            competition_code=code,
            commence_at=entry.event.commence_at,
            home_team_name=entry.event.home_name,
            away_team_name=entry.event.away_name,
            method=entry.decision.method or "kickoff",
            confidence=entry.decision.confidence,
            margin=entry.decision.margin,
            is_active=True,
            decided_at=moment,
            decided_by="import",
            note=None,
        )
    )
    db.flush()
    item.links_created += 1


def _reactivate_link(db: Session, entry: _PlannedEvent, item: LeagueOddsReport) -> None:
    """Une décision enregistrée n'est jamais reposée ; un report la réactive."""
    link = db.scalar(
        select(OddsEventLink).where(
            OddsEventLink.provider == PROVIDER,
            OddsEventLink.event_id == entry.event.event_id,
        )
    )
    if link is None or link.is_active:
        return
    _deactivate_other_links(db, link.match_id, item=item, keep_id=link.id)
    db.flush()
    link.is_active = True
    db.flush()


def _deactivate_other_links(
    db: Session,
    match_id: UUID,
    *,
    item: LeagueOddsReport,
    keep_id: UUID | None = None,
) -> None:
    rows = db.scalars(
        select(OddsEventLink).where(
            OddsEventLink.match_id == match_id,
            OddsEventLink.is_active.is_(True),
        )
    ).all()
    for row in rows:
        if keep_id is not None and row.id == keep_id:
            continue
        row.is_active = False
        item.links_deactivated += 1


def _write_odds(
    db: Session,
    match: Match,
    event_odds: NormalizedEventOdds,
    item: LeagueOddsReport,
) -> None:
    """Écrit les marchés et relevés sans jamais écraser une saisie manuelle."""
    for normalized in event_odds.markets:
        template = resolve_template(db, normalized.template_code)
        if template is None:
            item.warnings.append(
                f"Modèle de marché absent du catalogue : {normalized.template_code}."
            )
            continue

        line = normalized.line
        signature = build_signature(
            template_code=normalized.template_code,
            name=template.name,
            family=template.family,
            period=template.period,
            subject=template.subject,
            subject_team_id=None,
            subject_player=None,
            line=line,
            line2=None,
        )
        market = db.scalar(
            select(Market).where(
                Market.match_id == match.id,
                Market.signature == signature,
            )
        )
        if market is not None and market.is_custom:
            item.manual_kept += 1
            continue

        if market is None:
            market = Market(
                match_id=match.id,
                template_code=normalized.template_code,
                name=template.name,
                family=template.family,
                period=template.period,
                subject=template.subject,
                line=line,
                signature=signature,
                is_custom=False,
                notes=SOURCE,
                selections=[
                    Selection(
                        code=str(spec["code"]),
                        label=str(spec["label"]),
                        line=line,
                        sort_order=index,
                    )
                    for index, spec in enumerate(template.selection_templates)
                ],
            )
            db.add(market)
            db.flush()
            item.markets_written += 1

        selections = {selection.code: selection for selection in market.selections}
        for code, price in normalized.outcomes.items():
            selection = selections.get(code)
            if selection is None:
                item.warnings.append(
                    f"Issue hors catalogue ignorée pour {normalized.template_code} : {code}."
                )
                continue
            if _snapshot_exists(db, selection.id, event_odds.captured_at):
                continue
            db.add(
                OddsSnapshot(
                    selection_id=selection.id,
                    decimal_odds=price,
                    captured_at=event_odds.captured_at,
                    bookmaker=BOOKMAKER_LABEL,
                    source=SOURCE,
                )
            )
            item.snapshots_written += 1


def _snapshot_exists(db: Session, selection_id: UUID, captured_at: datetime) -> bool:
    moment = as_utc(captured_at)
    rows = db.scalars(
        select(OddsSnapshot).where(
            OddsSnapshot.selection_id == selection_id,
            OddsSnapshot.source == SOURCE,
        )
    ).all()
    return any(as_utc(row.captured_at) == moment for row in rows)


def _record_run(db: Session, report: OddsReport, moment: datetime) -> None:
    if report.status in {"applied", "empty"}:
        status = SyncStatus.APPLIED.value
    elif report.status == "partial":
        status = SyncStatus.PARTIAL.value
    else:
        status = SyncStatus.FAILED.value
    info = snapshot(db, PROVIDER, moment)
    db.add(
        SyncRun(
            provider=PROVIDER,
            operation=SyncOperation.ODDS.value,
            status=status,
            params={
                "leagues": [item.code for item in report.leagues],
                "extended_window_hours": EXTENDED_WINDOW_HOURS,
            },
            summary={
                **report.totals,
                "warnings": [
                    warning for item in report.leagues for warning in item.warnings
                ],
            },
            requests_used=report.requests,
            credits_used=report.credits_used,
            quota_remaining=info.remaining,
            error_message=(
                report.error or next((item.error or "" for item in report.leagues), "")
            )[:1000]
            or None,
            applied_at=moment,
        )
    )
    db.flush()


def overview(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """État de la source de cotes pour la page Synchronisation."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    info = snapshot(db, PROVIDER, moment)
    active_links = db.scalar(
        select(func.count())
        .select_from(OddsEventLink)
        .where(OddsEventLink.provider == PROVIDER, OddsEventLink.is_active.is_(True))
    ) or 0
    odds_rows = db.scalar(
        select(func.count())
        .select_from(OddsSnapshot)
        .where(OddsSnapshot.source == SOURCE)
    ) or 0
    markets = db.scalar(
        select(func.count(func.distinct(Market.id)))
        .select_from(Market)
        .join(Selection, Selection.market_id == Market.id)
        .join(OddsSnapshot, OddsSnapshot.selection_id == Selection.id)
        .where(OddsSnapshot.source == SOURCE)
    ) or 0
    competitions = db.scalars(
        select(Competition).where(Competition.code.in_(TRACKED_LEAGUES))
    ).all()
    by_code = {competition.code: competition for competition in competitions}
    upcoming: dict[str, int] = {}
    for code in TRACKED_LEAGUES:
        competition = by_code.get(code)
        if competition is None:
            upcoming[code] = 0
            continue
        upcoming[code] = int(
            db.scalar(
                select(func.count())
                .select_from(Match)
                .join(Season, Season.id == Match.season_id)
                .where(
                    Season.competition_id == competition.id,
                    Match.status == MatchStatus.PROGRAMME,
                    Match.kickoff_at >= moment,
                )
            )
            or 0
        )
    last_run = db.scalar(
        select(SyncRun)
        .where(SyncRun.provider == PROVIDER, SyncRun.operation == SyncOperation.ODDS.value)
        .order_by(SyncRun.created_at.desc())
        .limit(1)
    )
    return {
        "provider": PROVIDER,
        "configured": bool(settings.the_odds_api_key),
        "quota": {
            "used": info.used,
            "remaining": info.remaining,
            "limit": info.limit,
            "reset_at": info.reset_at,
        },
        "costs": {
            "competition": COMPETITION_CREDITS,
            "event": EVENT_CREDITS,
            "extended_window_hours": EXTENDED_WINDOW_HOURS,
            "extended_max_events": EXTENDED_MAX_EVENTS,
        },
        "totals": {
            "markets": int(markets),
            "odds_rows": int(odds_rows),
            "active_links": int(active_links),
        },
        "upcoming": upcoming,
        "last_run": last_run,
    }
