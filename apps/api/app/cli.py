"""Ligne de commande de synchronisation (phase 15, étape 6).

Six commandes, miroir exact des routes et des panneaux de la page
Synchronisation. Aucune logique n'est dupliquée : chaque commande appelle le
service utilisé par l'API.

    uv run python -m app.cli status
    uv run python -m app.cli facts --stats --standings
    uv run python -m app.cli csv-download
    uv run python -m app.cli csv-import
    uv run python -m app.cli odds-preview
    uv run python -m app.cli odds-import

Codes de sortie :

    0   appliqué, ou rien à faire
    1   échec
    2   erreur d'usage (argument invalide)
    3   partiel : une partie des compétitions a échoué

Aucune clé n'est affichée : les rapports ne contiennent que des compteurs et
des messages du fournisseur.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.connector import SyncRun
from app.services import auto_sync, csv_sync, odds_sync
from app.services import synchronization as facts

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_PARTIAL = 3

# Statuts qui ne demandent aucune reprise.
_OK = frozenset({"applied", "empty", "preview"})

_LABELS = {
    "applied": "appliqué",
    "partial": "partiel",
    "failed": "échec",
    "empty": "rien à faire",
    "preview": "aperçu",
    "skipped": "ignoré",
}

# Codes acceptés par commande, bornés aux compétitions réellement suivies.
_LEAGUES: dict[str, tuple[str, ...]] = {
    "facts": facts.TRACKED_LEAGUES,
    "csv-download": csv_sync.TRACKED_LEAGUES,
    "csv-import": csv_sync.TRACKED_LEAGUES,
    "odds-preview": odds_sync.TRACKED_LEAGUES,
    "odds-import": odds_sync.TRACKED_LEAGUES,
}


@contextmanager
def _session() -> Iterator[Session]:
    """Session courte : la CLI commite, comme la route ; sinon elle annule."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _configure_output() -> None:
    """Sortie UTF-8, y compris dans une tâche planifiée redirigée vers un fichier."""
    for stream in (sys.stdout, sys.stderr):
        cible: Any = stream
        with suppress(AttributeError, ValueError):
            cible.reconfigure(encoding="utf-8", errors="replace")


def _bounded(minimum: int, maximum: int) -> Any:
    def convert(raw: str) -> int:
        try:
            value = int(raw)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"nombre entier attendu, reçu « {raw} »"
            ) from None
        if not minimum <= value <= maximum:
            raise argparse.ArgumentTypeError(
                f"valeur attendue entre {minimum} et {maximum}"
            )
        return value

    return convert


def _parse_leagues(raw: str | None, allowed: tuple[str, ...]) -> list[str] | None:
    if not raw:
        return None
    codes: list[str] = []
    for part in raw.replace(";", ",").split(","):
        code = part.strip().lower()
        if not code:
            continue
        if code not in allowed:
            raise ValueError(
                f"compétition inconnue : « {part.strip()} ». "
                f"Codes acceptés : {', '.join(allowed)}."
            )
        if code not in codes:
            codes.append(code)
    return codes or None


def _n(value: int | float | None) -> str:
    """Nombre lisible : espace insécable fine comme séparateur de milliers."""
    if value is None:
        return "—"
    if isinstance(value, float) and not value.is_integer():
        texte = f"{value:.1f}"
    else:
        texte = f"{int(value):,}".replace(",", "\u202f")
    return texte


def _g(value: float | int | None) -> str:
    return "—" if value is None else f"{value:g}"


def _moment(value: datetime | None) -> str:
    if value is None:
        return "aucune"
    moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    local = moment.astimezone(ZoneInfo(settings.app_timezone))
    return local.strftime("%d/%m/%Y %H:%M")


def _label(status: str) -> str:
    return _LABELS.get(status, status)


def _code_for(status: str) -> int:
    if status in _OK:
        return EXIT_OK
    if status == "partial":
        return EXIT_PARTIAL
    return EXIT_FAILED


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))


# --- Rendu texte -----------------------------------------------------------


def _print_facts(report: facts.SyncReport) -> None:
    totals = report.totals
    print(f"Synchronisation BigBallsData — statut : {_label(report.status)}")
    if report.error:
        print(f"Erreur : {report.error}")
    print(
        f"Requêtes : {_n(report.requests)} · rencontres : {_n(totals['matches'])} "
        f"({_n(totals['created'])} créées, {_n(totals['updated'])} mises à jour)"
    )
    print(
        f"Statistiques : {_n(totals['stats_written'])} · "
        f"classements : {_n(totals['standings_written'])}"
    )
    if report.quota_remaining is not None:
        print(f"Quota restant : {_n(report.quota_remaining)}")
    for item in report.leagues:
        print(
            f"  {item.name} ({item.code}) : {_label(item.status)} — "
            f"{_n(item.matches)} rencontres, {_n(item.stats_written)} statistiques"
        )
        for warning in item.warnings:
            print(f"    ! {warning}")
        if item.error:
            print(f"    ! {item.error}")


def _print_csv_download(report: csv_sync.CsvDownloadReport) -> None:
    print(f"Téléchargement CSV — statut : {_label(report.status)}")
    print(f"Dossier : {report.directory or '—'}")
    if report.error:
        print(f"Erreur : {report.error}")
    for item in report.files:
        origine = "fichier local réutilisé" if item.reused else "téléchargé"
        print(
            f"  {item.name} ({item.division}) : {_label(item.status)} — "
            f"{_n(item.rows)} lignes ({origine})"
        )
        if item.error:
            print(f"    ! {item.error}")
        for warning in item.warnings:
            print(f"    ! {warning}")


def _print_csv_import(report: csv_sync.CsvReport) -> None:
    totals = report.totals
    print(f"Import CSV — statut : {_label(report.status)}")
    if report.error:
        print(f"Erreur : {report.error}")
    print(
        f"Lignes : {_n(totals['rows'])} · rattachées : {_n(totals['matched'])} · "
        f"ambiguës : {_n(totals['ambiguous'])} · "
        f"sans correspondance : {_n(totals['unmatched'])}"
    )
    print(
        f"xG écrits : {_n(totals['xg_written'])} · conservés : {_n(totals['xg_kept'])} · "
        f"marchés : {_n(totals['markets_written'])} · "
        f"relevés : {_n(totals['snapshots_written'])}"
    )
    for item in report.leagues:
        print(
            f"  {item.name} ({item.division}) : {_label(item.status)} — "
            f"{_n(item.rows)} lignes, {_n(item.matched)} rattachées"
        )
        for warning in item.warnings:
            print(f"    ! {warning}")
        if item.error:
            print(f"    ! {item.error}")


def _print_odds_preview(report: odds_sync.PreviewReport) -> None:
    print("Aperçu des cotes The Odds API — aucun crédit consommé.")
    print(f"Statut : {_label(report.status)}")
    if report.error:
        print(f"Erreur : {report.error}")
    print(f"Coût estimé : {_n(report.credits_estimated)} crédits")
    if report.quota_remaining is not None:
        print(f"Quota restant : {_n(report.quota_remaining)}")
    for item in report.leagues:
        print(
            f"  {item.name} ({item.code}) : {_n(item.events)} événements, "
            f"{_n(item.matched)} rattachés, {_n(item.ambiguous)} ambigus, "
            f"{_n(item.unmatched)} sans correspondance"
        )


def _print_odds_import(report: odds_sync.OddsReport) -> None:
    print(f"Import des cotes 1xBet — statut : {_label(report.status)}")
    if report.error:
        print(f"Erreur : {report.error}")
    print(
        f"Crédits utilisés : {_n(report.credits_used)} · "
        f"requêtes : {_n(report.requests)}"
    )
    if report.quota_remaining is not None:
        print(f"Quota restant : {_n(report.quota_remaining)}")
    for item in report.leagues:
        print(
            f"  {item.name} ({item.code}) : {_label(item.status)} — "
            f"{_n(item.events)} événements, {_n(item.matched)} rattachés, "
            f"{_n(item.markets_written)} marchés, {_n(item.credits)} crédits"
        )
        for warning in item.warnings:
            print(f"    ! {warning}")
        if item.error:
            print(f"    ! {item.error}")


def _run_line(run: SyncRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "status": run.status,
        "operation": run.operation,
        "created_at": run.created_at,
        "error": run.error_message,
    }


def _print_status(payload: dict[str, Any]) -> None:
    facts_state = payload["facts"]
    csv_state = payload["csv"]
    odds_state = payload["odds"]
    auto_state = payload["auto_sync"]

    print("État des sources — lecture seule, aucun appel réseau, aucun crédit.")
    quota = facts_state["quota"]
    totals = facts_state["totals"]
    print(
        f"BigBallsData : quota {_n(quota['used'])} / {_n(quota['limit'])} · "
        f"rencontres {_n(totals['matches'])} · équipes {_n(totals['teams'])} · "
        f"lignes xG {_n(totals['xg_rows'])}"
    )
    if not facts_state["configured"]:
        print("  ! Clé BigBallsData absente : la synchronisation des faits est indisponible.")

    csv_totals = csv_state["totals"]
    print(
        f"CSV : {_n(csv_totals['files'])} fichiers · "
        f"{_n(csv_totals['rows'])} lignes · "
        f"xG couverts {_n(csv_totals['matches_covered'])} · "
        f"en attente {_n(csv_totals['links_pending'])}"
    )
    print(f"  Dossier : {csv_state['directory']}")

    odds_quota = odds_state["quota"]
    odds_totals = odds_state["totals"]
    print(
        f"The Odds API : quota {_n(odds_quota['used'])} / {_n(odds_quota['limit'])} · "
        f"marchés {_n(odds_totals['markets'])} · "
        f"relevés {_n(odds_totals['odds_rows'])} · "
        f"liens actifs {_n(odds_totals['active_links'])}"
    )
    if not odds_state["configured"]:
        print("  ! Clé The Odds API absente : l'import des cotes est indisponible.")

    if auto_state["enabled"]:
        etat = "à lancer" if auto_state["due"] else "à jour"
        print(
            f"Mise à jour automatique : activée (seuil {_g(auto_state['interval_hours'])} h) "
            f"— {etat}"
        )
        print(
            "  Dernière passe de faits appliquée : "
            f"{_moment(auto_state['last_applied_at'])}"
        )
    else:
        print("Mise à jour automatique : désactivée (AUTO_SYNC_ENABLED=false).")

    derniers = payload.get("last_runs") or {}
    for nom, run in derniers.items():
        if run is None:
            print(f"Dernier journal {nom} : aucun")
        else:
            print(
                f"Dernier journal {nom} : {_label(str(run['status']))} "
                f"le {_moment(run['created_at'])}"
            )


# --- Commandes -------------------------------------------------------------


def _cmd_facts(args: argparse.Namespace) -> int:
    with _session() as db:
        report = facts.run_sync(
            db,
            leagues=args.leagues,
            include_stats=args.stats,
            include_standings=args.standings,
            stats_limit=args.stats_limit,
        )
        db.commit()
    if args.json:
        _print_json(report.as_dict())
    else:
        _print_facts(report)
    return _code_for(report.status)


def _cmd_csv_download(args: argparse.Namespace) -> int:
    with _session() as db:
        report = csv_sync.download(db, leagues=args.leagues)
        db.commit()
    if args.json:
        _print_json(report.as_dict())
    else:
        _print_csv_download(report)
    return _code_for(report.status)


def _cmd_csv_import(args: argparse.Namespace) -> int:
    with _session() as db:
        report = csv_sync.run(db, leagues=args.leagues, refresh=not args.no_refresh)
        db.commit()
    if args.json:
        _print_json(report.as_dict())
    else:
        _print_csv_import(report)
    return _code_for(report.status)


def _cmd_odds_preview(args: argparse.Namespace) -> int:
    with _session() as db:
        report = odds_sync.preview(
            db,
            leagues=args.leagues,
            include_extended=not args.no_extended,
            extended_limit=args.extended_limit,
        )
    if args.json:
        _print_json(report.as_dict())
    else:
        _print_odds_preview(report)
    return _code_for(report.status)


def _cmd_odds_import(args: argparse.Namespace) -> int:
    with _session() as db:
        report = odds_sync.run(
            db,
            leagues=args.leagues,
            include_extended=not args.no_extended,
            extended_limit=args.extended_limit,
        )
        db.commit()
    if args.json:
        _print_json(report.as_dict())
    else:
        _print_odds_import(report)
    return _code_for(report.status)


def _cmd_status(args: argparse.Namespace) -> int:
    with _session() as db:
        facts_overview = facts.overview(db)
        csv_overview = csv_sync.overview(db)
        odds_overview = odds_sync.overview(db)
        last_runs = {
            "faits": _run_line(auto_sync.last_run(db)),
            "csv": _run_line(csv_overview.get("last_run")),
            "cotes": _run_line(odds_overview.get("last_run")),
        }
        auto_state = {
            "enabled": settings.auto_sync_enabled,
            "interval_hours": settings.auto_sync_interval_hours,
            "due": auto_sync.is_due(db),
            "last_applied_at": auto_sync.last_applied_at(db),
        }
    payload = {
        "facts": {key: value for key, value in facts_overview.items() if key != "runs"},
        "csv": {
            key: value for key, value in csv_overview.items() if key != "last_run"
        },
        "odds": {
            key: value for key, value in odds_overview.items() if key != "last_run"
        },
        "auto_sync": auto_state,
        "last_runs": last_runs,
    }
    if args.json:
        _print_json(payload)
    else:
        _print_status(payload)
    return EXIT_OK


# --- Analyse des arguments -------------------------------------------------


def _add_leagues(parser: argparse.ArgumentParser, allowed: tuple[str, ...]) -> None:
    parser.add_argument(
        "--leagues",
        metavar="CODES",
        help=(
            "compétitions à traiter, séparées par des virgules "
            f"({', '.join(allowed)}) ; par défaut, toutes"
        ),
    )


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="affiche le rapport complet en JSON, sans secret",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description=(
            "Synchronisation ODDS ANALYST : faits BigBallsData, xG et cotes de "
            "clôture (CSV), cotes 1xBet (The Odds API)."
        ),
        epilog=(
            "Codes de sortie : 0 appliqué ou rien à faire, 1 échec, "
            "2 argument invalide, 3 partiel."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMANDE")

    p_facts = sub.add_parser(
        "facts",
        help="importe calendrier, résultats, classements et statistiques",
        description="Passe de faits BigBallsData, identique au bouton de la page.",
    )
    _add_leagues(p_facts, facts.TRACKED_LEAGUES)
    p_facts.add_argument(
        "--stats",
        action="store_true",
        help="importe aussi les statistiques détaillées (coûte des requêtes)",
    )
    p_facts.add_argument(
        "--standings",
        action="store_true",
        help="importe aussi les classements",
    )
    p_facts.add_argument(
        "--stats-limit",
        type=_bounded(0, facts.STATS_MAX),
        default=20,
        metavar="N",
        help=(
            "nombre de rencontres par compétition pour les statistiques "
            f"(0-{facts.STATS_MAX}, défaut 20)"
        ),
    )
    _add_json(p_facts)
    p_facts.set_defaults(handler=_cmd_facts)

    p_download = sub.add_parser(
        "csv-download",
        help="télécharge les fichiers CSV publics, sans écrire en base",
        description="Télécharge les cinq fichiers puis les conserve ; lecture seule en base.",
    )
    _add_leagues(p_download, csv_sync.TRACKED_LEAGUES)
    _add_json(p_download)
    p_download.set_defaults(handler=_cmd_csv_download)

    p_import = sub.add_parser(
        "csv-import",
        help="écrit le xG et les cotes de clôture des rencontres terminées",
        description="Apparie et écrit le xG et la clôture moyenne ; jamais un écrasement.",
    )
    _add_leagues(p_import, csv_sync.TRACKED_LEAGUES)
    p_import.add_argument(
        "--no-refresh",
        action="store_true",
        help="réutilise les fichiers déjà téléchargés au lieu de les rafraîchir",
    )
    _add_json(p_import)
    p_import.set_defaults(handler=_cmd_csv_import)

    p_preview = sub.add_parser(
        "odds-preview",
        help="aperçu gratuit de l'appariement des cotes, sans crédit",
        description="Relevé à blanc : décisions d'appariement et coût estimé, sans écriture.",
    )
    _add_leagues(p_preview, odds_sync.TRACKED_LEAGUES)
    p_preview.add_argument(
        "--no-extended",
        action="store_true",
        help="ne demande pas les marchés étendus (moins de crédits)",
    )
    p_preview.add_argument(
        "--extended-limit",
        type=_bounded(0, odds_sync.EXTENDED_MAX_EVENTS),
        default=odds_sync.EXTENDED_MAX_EVENTS,
        metavar="N",
        help=(
            "nombre maximal d'événements étendus "
            f"(0-{odds_sync.EXTENDED_MAX_EVENTS}, défaut {odds_sync.EXTENDED_MAX_EVENTS})"
        ),
    )
    _add_json(p_preview)
    p_preview.set_defaults(handler=_cmd_odds_preview)

    p_odds = sub.add_parser(
        "odds-import",
        help="importe les cotes 1xBet des rencontres à venir (crédits payants)",
        description=(
            "Commande explicite : consomme des crédits The Odds API. "
            "Utilisez odds-preview pour connaître le coût avant d'importer."
        ),
    )
    _add_leagues(p_odds, odds_sync.TRACKED_LEAGUES)
    p_odds.add_argument(
        "--no-extended",
        action="store_true",
        help="ne demande pas les marchés étendus (moins de crédits)",
    )
    p_odds.add_argument(
        "--extended-limit",
        type=_bounded(0, odds_sync.EXTENDED_MAX_EVENTS),
        default=odds_sync.EXTENDED_MAX_EVENTS,
        metavar="N",
        help=(
            "nombre maximal d'événements étendus "
            f"(0-{odds_sync.EXTENDED_MAX_EVENTS}, défaut {odds_sync.EXTENDED_MAX_EVENTS})"
        ),
    )
    _add_json(p_odds)
    p_odds.set_defaults(handler=_cmd_odds_import)

    p_status = sub.add_parser(
        "status",
        help="état des trois sources, sans appel réseau",
        description=(
            "Lit la base et le disque : quota, fichiers, couverture xG, lignes "
            "en attente. Aucun crédit, aucune écriture."
        ),
    )
    _add_json(p_status)
    p_status.set_defaults(handler=_cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    parser = build_parser()
    args = parser.parse_args(argv)

    allowed = _LEAGUES.get(args.command)
    if allowed is not None:
        try:
            args.leagues = _parse_leagues(args.leagues, allowed)
        except ValueError as exc:
            parser.error(str(exc))

    try:
        return int(args.handler(args))
    except KeyboardInterrupt:
        print("Interrompu par l'utilisateur.", file=sys.stderr)
        return EXIT_FAILED
    except Exception as exc:
        print(f"Échec : {exc.__class__.__name__} — {exc}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
