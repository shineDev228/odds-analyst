"""Collecte des snapshots quotidiens (phase 14A, étapes 3 et 4).

Le service écrit une ligne par équipe et par jour dans ``team_snapshots`` et,
au plus deux relevés par rencontre cotée dans ``market_board_snapshots``. Il ne
calcule aucun Elo, ne tire aucune conclusion et ne touche ni au moteur ni à
l'interface.

Une passe équipes est idempotente : sans ``force``, une équipe déjà relevée le
jour même est sautée sans appel HTTP. Un rejeu du même créneau de board met à
jour la ligne existante. Le journal ``sync_runs`` reçoit une seule ligne par
passe, avec ``operation = "snapshots"``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import (
    BudgetExceededError,
    ConnectorError,
    ProviderAuthError,
    ProviderRateLimitError,
)
from app.connectors.bigballsdata.importer import PROVIDER
from app.connectors.bigballsdata.snapshot_importer import (
    upsert_board_snapshot,
    upsert_team_snapshot,
)
from app.connectors.bigballsdata.snapshot_mapping import (
    SLOTS,
    map_market_board_snapshot,
    map_team_snapshot,
)
from app.connectors.quota import consume, ensure_budget, get_usage, snapshot
from app.core.config import settings
from app.models.connector import SyncOperation, SyncRun, SyncStatus
from app.models.match import Match
from app.models.reference import Competition, Season, Team
from app.models.snapshot import TeamSnapshot
from app.services.synchronization import TRACKED_LEAGUES, make_client

TEAM_ENDPOINTS = (
    ("elo", "get_team_elo", "Elo"),
    ("stats", "get_team_stats", "statistiques"),
    ("season", "get_team_season", "saison"),
)


@dataclass(slots=True)
class TeamCollectionReport:
    """Compteurs de la collecte des équipes."""

    selected: int = 0
    written: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    partial: int = 0
    failed: int = 0
    requests: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "selectionnees": self.selected,
            "ecrites": self.written,
            "creees": self.created,
            "mises_a_jour": self.updated,
            "inchangees": self.unchanged,
            "sautees": self.skipped,
            "partielles": self.partial,
            "echecs": self.failed,
            "requetes": self.requests,
            "avertissements": list(self.warnings),
        }


@dataclass(slots=True)
class BoardCollectionReport:
    """Compteurs du board marché."""

    received: int = 0
    matched: int = 0
    written: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    no_odds: int = 0
    too_late: int = 0
    not_upcoming: int = 0
    no_schedule: int = 0
    no_values: int = 0
    unmatched: int = 0
    ignored: int = 0
    requests: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "recues": self.received,
            "rattachees": self.matched,
            "ecrites": self.written,
            "creees": self.created,
            "mises_a_jour": self.updated,
            "inchangees": self.unchanged,
            "sans_cotes": self.no_odds,
            "trop_tard": self.too_late,
            "non_programmees": self.not_upcoming,
            "sans_horaire": self.no_schedule,
            "sans_valeur": self.no_values,
            "sans_correspondance": self.unmatched,
            "ignorees": self.ignored,
            "requetes": self.requests,
            "avertissements": list(self.warnings),
        }


@dataclass(slots=True)
class SnapshotReport:
    """Rapport d'une passe, sérialisable sans secret."""

    provider: str = PROVIDER
    status: str = "applied"
    slot: str = "morning"
    requests: int = 0
    quota_remaining: int | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    teams: TeamCollectionReport = field(default_factory=TeamCollectionReport)
    board: BoardCollectionReport = field(default_factory=BoardCollectionReport)
    # Classements écrits par la passe de faits qui précède, pour le rapport du matin.
    facts_standings: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "slot": self.slot,
            "requests": self.requests,
            "quota_remaining": self.quota_remaining,
            "error": self.error,
            "classements": self.facts_standings,
            "avertissements": list(self.warnings),
            "equipes": self.teams.as_dict(),
            "board": self.board.as_dict(),
        }


def run_snapshots(
    db: Session,
    *,
    leagues: list[str] | None = None,
    force: bool = False,
    slot: str = "morning",
    include_teams: bool = True,
    include_board: bool = False,
    facts_standings: int = 0,
    now: datetime | None = None,
    client: Any | None = None,
    sleep: Any = time.sleep,
) -> SnapshotReport:
    """Collecte les snapshots demandés et journalise la passe.

    ``include_teams`` et ``include_board`` permettent de composer la passe du
    matin (équipes + board) et celle du soir (board seul). ``slot`` détermine
    le créneau du board : ``morning`` ou ``evening``. ``facts_standings``
    recopie dans le journal les classements écrits par la passe de faits qui
    précède, sans rien recalculer.

    Ne valide pas la transaction : l'appelant décide du ``commit``.
    """
    del sleep  # Le client HTTP gère déjà l'espacement entre deux appels.
    if slot not in SLOTS:
        raise ValueError(f"Créneau inconnu : {slot}. Valeurs : {', '.join(SLOTS)}.")
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    codes = _selected_codes(leagues)
    report = SnapshotReport(slot=slot, facts_standings=facts_standings)
    teams = (
        _select_teams(db, codes if leagues is not None else None) if include_teams else []
    )
    report.teams.selected = len(teams)
    if not teams and not include_board:
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

        stopped = False
        if teams:
            stopped = _run_teams(
                db,
                connector,
                teams=teams,
                moment=moment,
                report=report,
                force=force,
            )
        if include_board and not stopped:
            try:
                _run_board(
                    db,
                    connector,
                    codes=codes,
                    slot=slot,
                    moment=moment,
                    report=report,
                )
            except ProviderAuthError as exc:
                report.status = "failed"
                report.error = exc.message
            except (BudgetExceededError, ProviderRateLimitError) as exc:
                if report.status != "failed":
                    report.status = "partial"
                report.error = exc.message

        if report.status == "applied" and report.teams.failed:
            report.status = "partial"
            report.error = report.error or (
                "Certaines équipes n'ont pas pu être collectées : voir les avertissements."
            )
        calls = report.teams.requests + report.board.requests
        if (
            calls > 0
            and report.status != "failed"
            and _check_usage(db, connector, moment=moment, report=report)
        ):
            calls += 1
        report.requests = calls
    finally:
        if own_client and connector is not None:
            connector.close()
        report.quota_remaining = snapshot(db, PROVIDER, moment).remaining
        _record_run(db, report, moment, leagues)
    return report


def _run_teams(
    db: Session,
    client: Any,
    *,
    teams: list[Team],
    moment: datetime,
    report: SnapshotReport,
    force: bool,
) -> bool:
    """Collecte les équipes ; retourne ``True`` si la passe doit s'arrêter."""
    day = _paris_day(moment, report.warnings)
    existing = _existing_team_ids(db, day)
    for team in teams:
        if not force and team.id in existing:
            # Déjà relevée aujourd'hui : trois requêtes économisées.
            report.teams.skipped += 1
            continue
        try:
            _collect_team(
                db,
                client,
                team=team,
                moment=moment,
                item=report.teams,
            )
        except ProviderAuthError as exc:
            # Clé refusée : inutile de tenter les autres équipes.
            report.status = "failed"
            report.error = exc.message
            return True
        except (BudgetExceededError, ProviderRateLimitError) as exc:
            # Budget ou quota épuisé : arrêt propre, reprise le lendemain.
            report.status = "partial"
            report.error = exc.message
            return True
    return False


def _selected_codes(leagues: list[str] | None) -> list[str]:
    candidates = leagues if leagues is not None else list(TRACKED_LEAGUES)
    return [code for code in candidates if code in TRACKED_LEAGUES]


def _select_teams(db: Session, leagues: list[str] | None) -> list[Team]:
    """Équipes pourvues d'un identifiant fournisseur, jamais inventées."""
    statement = (
        select(Team).where(Team.external_id.is_not(None)).order_by(Team.name)
    )
    if leagues is not None:
        home = (
            select(Match.home_team_id.label("team_id"))
            .join(Season, Match.season_id == Season.id)
            .join(Competition, Season.competition_id == Competition.id)
            .where(Season.is_current.is_(True), Competition.code.in_(leagues))
        )
        away = (
            select(Match.away_team_id.label("team_id"))
            .join(Season, Match.season_id == Season.id)
            .join(Competition, Season.competition_id == Competition.id)
            .where(Season.is_current.is_(True), Competition.code.in_(leagues))
        )
        members = home.union(away).subquery()
        statement = statement.where(Team.id.in_(select(members.c.team_id)))
    return list(db.scalars(statement).all())


def _existing_team_ids(db: Session, day: date) -> set[Any]:
    return set(
        db.scalars(
            select(TeamSnapshot.team_id).where(TeamSnapshot.captured_on == day)
        ).all()
    )


def _collect_team(
    db: Session,
    client: Any,
    *,
    team: Team,
    moment: datetime,
    item: TeamCollectionReport,
) -> None:
    external_id = team.external_id
    if external_id is None:  # défense : la sélection l'exclut déjà
        item.failed += 1
        item.warnings.append(f"{team.name} : identifiant fournisseur absent, ignorée.")
        return

    payloads: dict[str, Any] = {}
    missing = 0
    for key, method, label in TEAM_ENDPOINTS:
        ensure_budget(db, PROVIDER, 1, now=moment)
        fetch = getattr(client, method)
        try:
            payloads[key] = fetch(external_id)
        except (BudgetExceededError, ProviderRateLimitError, ProviderAuthError):
            raise
        except ConnectorError:
            # 404/400 ou panne réseau : les deux autres endpoints sont tentés.
            missing += 1
            item.warnings.append(
                f"{team.name} : {label} indisponible chez le fournisseur."
            )
            continue
        consume(db, PROVIDER, 1, now=moment)
        item.requests += 1

    if missing == len(TEAM_ENDPOINTS):
        item.failed += 1
        item.warnings.append(
            f"{team.name} : aucun endpoint disponible, aucune ligne écrite."
        )
        return

    value = map_team_snapshot(
        team_external_id=external_id,
        elo=payloads.get("elo"),
        stats=payloads.get("stats"),
        season=payloads.get("season"),
        captured_at=moment,
        timezone=settings.app_timezone,
    )
    item.warnings.extend(f"{team.name} : {warning}" for warning in value.warnings)
    action = upsert_team_snapshot(db, team=team, snapshot=value)
    item.written += 1
    if action == "created":
        item.created += 1
    elif action == "updated":
        item.updated += 1
    else:
        item.unchanged += 1
    if missing:
        item.partial += 1


def _run_board(
    db: Session,
    client: Any,
    *,
    codes: list[str],
    slot: str,
    moment: datetime,
    report: SnapshotReport,
) -> None:
    """Relève les cotes agrégées des rencontres à venir, pour un créneau."""
    item = report.board
    dates = (moment.date(), moment.date() + timedelta(days=1))
    games: dict[str, dict[str, Any]] = {}
    for code in codes:
        for day in dates:
            ensure_budget(db, PROVIDER, 1, now=moment)
            try:
                rows = client.list_games(league=code, day=day.isoformat())
            except (BudgetExceededError, ProviderRateLimitError, ProviderAuthError):
                raise
            except ConnectorError:
                # Une compétition ou une date refusée ne bloque pas les autres.
                item.warnings.append(
                    f"Board indisponible pour {code} le {day.isoformat()}."
                )
                continue
            consume(db, PROVIDER, 1, now=moment)
            item.requests += 1
            for row in rows:
                if not isinstance(row, dict):
                    item.ignored += 1
                    continue
                game_id = row.get("game_id")
                if not game_id:
                    item.ignored += 1
                    continue
                # Une même rencontre peut apparaître sur deux fenêtres.
                games[str(game_id)] = row

    if not games:
        return
    item.received = len(games)
    matches = _matches_by_external_id(db, list(games))
    for game_id, game in games.items():
        match = matches.get(game_id)
        if match is None:
            # Aucune création : le board ne fabrique jamais une rencontre.
            item.unmatched += 1
            continue
        item.matched += 1
        value = map_market_board_snapshot(
            game=game,
            slot=slot,
            captured_at=moment,
            timezone=settings.app_timezone,
        )
        item.warnings.extend(f"{game_id} : {warning}" for warning in value.warnings)
        if not isinstance(game.get("odds"), dict):
            item.no_odds += 1
            continue
        if value.scheduled_at is None:
            item.no_schedule += 1
            continue
        if value.scheduled_at <= moment:
            # Jamais de relevé après le coup d'envoi.
            item.too_late += 1
            continue
        if value.status != "upcoming":
            item.not_upcoming += 1
            continue
        if not value.has_values:
            # Une ligne sans aucune cote n'apporte rien.
            item.no_values += 1
            continue
        action = upsert_board_snapshot(db, match=match, snapshot=value)
        item.written += 1
        if action == "created":
            item.created += 1
        elif action == "updated":
            item.updated += 1
        else:
            item.unchanged += 1


def _matches_by_external_id(db: Session, external_ids: list[str]) -> dict[str, Match]:
    rows = db.scalars(select(Match).where(Match.external_id.in_(external_ids))).all()
    return {row.external_id: row for row in rows if row.external_id}


def _paris_day(moment: datetime, warnings: list[str]) -> date:
    try:
        zone = ZoneInfo(settings.app_timezone)
    except (KeyError, ValueError):
        warnings.append(
            f"Fuseau « {settings.app_timezone} » inconnu : Europe/Paris utilisé."
        )
        zone = ZoneInfo("Europe/Paris")
    return moment.astimezone(zone).date()


def _check_usage(
    db: Session, client: Any, *, moment: datetime, report: SnapshotReport
) -> bool:
    """Recale le compteur local sur le quota réel ; jamais un motif d'échec.

    Retourne ``True`` si une requête a réellement été consommée.
    """
    try:
        ensure_budget(db, PROVIDER, 1, now=moment)
    except BudgetExceededError:
        report.warnings.append("Quota réel non vérifié : budget local épuisé.")
        return False
    try:
        payload = client.get_usage()
    except ConnectorError:
        report.warnings.append("Quota réel indisponible : compteur local conservé.")
        return False
    consume(db, PROVIDER, 1, now=moment)
    remaining = _remaining_from_usage(payload)
    if remaining is None:
        report.warnings.append("Réponse /v1/usage illisible : compteur local conservé.")
        return True
    usage = get_usage(db, PROVIDER, moment)
    # Le budget du projet (1 800) ne peut que se resserrer : jamais le dépasser,
    # même si le fournisseur annonce un plafond plus large (2 000 par jour).
    usage.limit = min(usage.limit, usage.used + max(remaining, 0))
    db.flush()
    return True


def _remaining_from_usage(payload: Any) -> int | None:
    """Lit un restant sans supposer un nom de champ unique."""
    if not isinstance(payload, dict):
        return None
    for container in (payload, payload.get("quota"), payload.get("usage")):
        if not isinstance(container, dict):
            continue
        for key in (
            "remaining_today",
            "remaining",
            "quota_remaining",
            "requests_remaining",
            "requests_left",
        ):
            if key not in container:
                continue
            value = container[key]
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                try:
                    return int(float(value))
                except ValueError:
                    continue
    return None


def _record_run(
    db: Session,
    report: SnapshotReport,
    moment: datetime,
    leagues: list[str] | None,
) -> None:
    if report.status == "partial":
        status = SyncStatus.PARTIAL.value
    elif report.status == "failed":
        status = SyncStatus.FAILED.value
    else:
        status = SyncStatus.APPLIED.value
    db.add(
        SyncRun(
            provider=PROVIDER,
            operation=SyncOperation.SNAPSHOTS.value,
            status=status,
            params={
                "league": ",".join(leagues) if leagues else "toutes",
                "season": settings.bigballsdata_season,
                "slot": report.slot,
            },
            summary={
                "classements": report.facts_standings,
                "equipes": report.teams.as_dict(),
                "board": report.board.as_dict(),
                "avertissements": list(report.warnings),
            },
            requests_used=report.requests,
            credits_used=0,
            quota_remaining=report.quota_remaining,
            error_message=(report.error or "")[:1000] or None,
            applied_at=moment,
        )
    )
    db.flush()


__all__ = [
    "BoardCollectionReport",
    "SnapshotReport",
    "TeamCollectionReport",
    "run_snapshots",
]
