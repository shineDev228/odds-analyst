"""Enrichissement CSV : xG et cotes de clôture (football-data.co.uk).

Trois principes, les mêmes que pour les cotes :

1. **Le fichier est une observation, pas une vérité.** Il est daté, empreinté
   (sha256) et conservé sur le disque ; une passe sans réseau réutilise le
   dernier fichier connu au lieu d'échouer.
2. **La rencontre est trouvée par son résultat.** Date, score final et mi-temps
   forment la clé ; le nom ne confirme que le sens domicile/extérieur. En cas
   de doute (marge inférieure à 0,25), la ligne reste `pending` et **rien**
   n'est écrit.
3. **Rien n'est écrasé.** Un xG déjà présent est conservé, un marché saisi à la
   main est ignoré, un relevé identique n'est pas réécrit. Seule la moyenne du
   marché est enregistrée, sous le libellé « Clôture (moyenne) ».

Le fournisseur est public et gratuit : aucune clé, aucun quota. Cinq
compétitions sont couvertes (celles dont les fichiers publient le xG) ; la MLS
et la Ligue des champions n'en publient pas et sont laissées de côté.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.connectors.base import ConnectorError
from app.connectors.csv_matching import CsvCandidate, CsvDecision, decide_row
from app.connectors.football_data_uk.client import FootballDataUkClient
from app.connectors.football_data_uk.csvar import decode_bytes
from app.connectors.football_data_uk.mapping import (
    ClosingOdds,
    CsvRow,
    division_label,
    parse_rows,
)
from app.connectors.http import HttpClient
from app.core.config import PROJECT_ROOT, settings
from app.models.connector import SyncOperation, SyncRun, SyncStatus
from app.models.link import CsvLink
from app.models.market import Market, OddsSnapshot, Selection
from app.models.match import Match, MatchStatus, TeamMatchStats
from app.models.reference import Competition, Season
from app.services.markets import as_utc, build_signature, resolve_template

PROVIDER = "football_data_uk"
SOURCE = "csv"
BOOKMAKER_LABEL = "Clôture (moyenne)"
# Seules les compétitions dont le fichier public contient le xG.
DIVISIONS: dict[str, str] = {
    "ligue1": "F1",
    "laliga": "SP1",
    "epl": "E0",
    "seriea": "I1",
    "bundesliga": "D1",
}
TRACKED_LEAGUES = tuple(DIVISIONS)
TOTAL_LINE = 2.5
# Espacement des téléchargements : cinq fichiers, jamais en rafale.
MIN_INTERVAL_SECONDS = 0.5
STORAGE_DIR = PROJECT_ROOT / "data" / "local" / "csv"
RESULT_TEMPLATE = "football.resultat_1x2"
TOTAL_TEMPLATE = "football.total_buts"


@dataclass(slots=True)
class CsvFileReport:
    """Un fichier téléchargé, réutilisé ou indisponible."""

    code: str
    division: str
    name: str
    status: str = "applied"
    season_label: str | None = None
    path: str | None = None
    sha256: str | None = None
    size_bytes: int = 0
    rows: int = 0
    downloaded_at: datetime | None = None
    reused: bool = False
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "division": self.division,
            "name": self.name,
            "status": self.status,
            "season_label": self.season_label,
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "rows": self.rows,
            "downloaded_at": self.downloaded_at,
            "reused": self.reused,
            "error": self.error,
            "warnings": list(self.warnings),
        }


@dataclass(slots=True)
class CsvLeagueReport:
    """Ce qu'une compétition a reçu pendant la passe."""

    code: str
    division: str
    name: str
    status: str = "applied"
    rows: int = 0
    matched: int = 0
    ambiguous: int = 0
    unmatched: int = 0
    links_created: int = 0
    links_reused: int = 0
    ignored: int = 0
    xg_written: int = 0
    xg_kept: int = 0
    stats_created: int = 0
    odds_missing: int = 0
    markets_written: int = 0
    snapshots_written: int = 0
    manual_kept: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "division": self.division,
            "name": self.name,
            "status": self.status,
            "rows": self.rows,
            "matched": self.matched,
            "ambiguous": self.ambiguous,
            "unmatched": self.unmatched,
            "links_created": self.links_created,
            "links_reused": self.links_reused,
            "ignored": self.ignored,
            "xg_written": self.xg_written,
            "xg_kept": self.xg_kept,
            "stats_created": self.stats_created,
            "odds_missing": self.odds_missing,
            "markets_written": self.markets_written,
            "snapshots_written": self.snapshots_written,
            "manual_kept": self.manual_kept,
            "warnings": list(self.warnings),
            "error": self.error,
        }


@dataclass(slots=True)
class CsvReport:
    provider: str = PROVIDER
    status: str = "applied"
    directory: str = ""
    error: str | None = None
    files: list[CsvFileReport] = field(default_factory=list)
    leagues: list[CsvLeagueReport] = field(default_factory=list)

    @property
    def totals(self) -> dict[str, int]:
        return {
            "rows": sum(item.rows for item in self.leagues),
            "matched": sum(item.matched for item in self.leagues),
            "ambiguous": sum(item.ambiguous for item in self.leagues),
            "unmatched": sum(item.unmatched for item in self.leagues),
            "links_created": sum(item.links_created for item in self.leagues),
            "links_reused": sum(item.links_reused for item in self.leagues),
            "xg_written": sum(item.xg_written for item in self.leagues),
            "xg_kept": sum(item.xg_kept for item in self.leagues),
            "stats_created": sum(item.stats_created for item in self.leagues),
            "markets_written": sum(item.markets_written for item in self.leagues),
            "snapshots_written": sum(item.snapshots_written for item in self.leagues),
            "manual_kept": sum(item.manual_kept for item in self.leagues),
            "odds_missing": sum(item.odds_missing for item in self.leagues),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "directory": self.directory,
            "error": self.error,
            "files": [item.as_dict() for item in self.files],
            "totals": self.totals,
            "leagues": [item.as_dict() for item in self.leagues],
        }


@dataclass(slots=True)
class CsvDownloadReport:
    provider: str = PROVIDER
    status: str = "applied"
    directory: str = ""
    error: str | None = None
    files: list[CsvFileReport] = field(default_factory=list)

    @property
    def totals(self) -> dict[str, int]:
        return {
            "files": sum(1 for item in self.files if item.status != "failed"),
            "rows": sum(item.rows for item in self.files),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "directory": self.directory,
            "error": self.error,
            "totals": self.totals,
            "files": [item.as_dict() for item in self.files],
        }


@dataclass(slots=True)
class _Prepared:
    """Fichier prêt à être rapproché, avec sa compétition et sa saison."""

    report: CsvFileReport
    competition: Competition | None
    season: Season | None
    rows: list[CsvRow]


def make_client() -> FootballDataUkClient:
    """Client public : aucune clé, aucun quota, un appel toutes les 0,5 s."""
    http = HttpClient(
        timeout=settings.connector_timeout_seconds,
        max_retries=settings.connector_max_retries,
        min_interval=MIN_INTERVAL_SECONDS,
    )
    return FootballDataUkClient(base_url=settings.football_data_uk_base_url, http=http)


def storage_dir() -> Path:
    """Dossier des fichiers téléchargés, hors dépôt Git (`data/local/`)."""
    configure = (settings.csv_storage_dir or "").strip()
    return Path(configure) if configure else STORAGE_DIR


def _selected(leagues: list[str] | None) -> list[str]:
    return [code for code in (leagues or TRACKED_LEAGUES) if code in DIVISIONS]


def _season(db: Session, code: str) -> tuple[Competition, Season] | None:
    """Compétition et saison courante du fournisseur de faits."""
    row = db.execute(
        select(Competition, Season)
        .join(Season, Season.competition_id == Competition.id)
        .where(Competition.code == code, Season.is_current.is_(True))
        .order_by(Season.start_date.desc().nullslast(), Season.label.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return row[0], row[1]


def _paths(division: str) -> tuple[Path, Path]:
    racine = storage_dir()
    return racine / f"{division}.csv", racine / f"{division}.json"


def _read_sidecar(division: str) -> dict[str, Any] | None:
    _, meta_path = _paths(division)
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _store(division: str, content: bytes, rows: int, moment: datetime) -> tuple[str, int]:
    """Écrit le fichier et son empreinte ; renvoie (sha256, taille)."""
    fichier, meta_path = _paths(division)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_bytes(content)
    empreinte = hashlib.sha256(content).hexdigest()
    meta_path.write_text(
        json.dumps(
            {
                "division": division,
                "sha256": empreinte,
                "size_bytes": len(content),
                "rows": rows,
                "downloaded_at": moment.isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return empreinte, len(content)


def _stored(division: str) -> tuple[bytes | None, dict[str, Any] | None]:
    fichier, _ = _paths(division)
    if not fichier.exists():
        return None, None
    try:
        return fichier.read_bytes(), _read_sidecar(division)
    except OSError:
        return None, None


def _prepare_files(
    db: Session,
    client: FootballDataUkClient,
    selected: list[str],
    moment: datetime,
    *,
    refresh: bool,
) -> list[_Prepared]:
    """Télécharge (ou relit) chaque fichier et le prépare pour l'appariement.

    Un échec réseau n'annule pas la passe : le dernier fichier connu est
    réutilisé et l'avertissement reste visible dans le journal.
    """
    prepared: list[_Prepared] = []
    for code in selected:
        division = DIVISIONS[code]
        item = CsvFileReport(
            code=code,
            division=division,
            name=division_label(division),
        )
        fiche = _season(db, code)
        if fiche is None:
            item.status = "skipped"
            item.error = (
                "Compétition absente de la base : lancez d'abord une synchronisation "
                "des faits (BigBallsData)."
            )
            prepared.append(
                _Prepared(report=item, competition=None, season=None, rows=[])
            )
            continue
        competition, season = fiche
        item.season_label = season.label

        contenu: bytes | None = None
        rows: list[CsvRow] = []
        local, meta = _stored(division)
        if not refresh and local is not None and meta is not None:
            try:
                rows = parse_rows(decode_bytes(local), division=division)
            except ConnectorError as exc:
                item.warnings.append(exc.message)
            else:
                contenu = local
                item.reused = True
                item.sha256 = str(meta.get("sha256") or "")
                item.rows = len(rows)
                item.downloaded_at = _parse_moment(meta.get("downloaded_at"))

        if contenu is None:
            try:
                contenu, rows = client.fetch_file(
                    division=division, season=season.label
                )
            except ConnectorError as exc:
                if local is not None:
                    try:
                        rows = parse_rows(decode_bytes(local), division=division)
                    except ConnectorError as read_error:
                        item.status = "failed"
                        item.error = f"{exc.message} {read_error.message}"
                    else:
                        contenu = local
                        item.status = "partial"
                        item.reused = True
                        item.sha256 = str((meta or {}).get("sha256") or "")
                        item.rows = len(rows)
                        item.downloaded_at = _parse_moment((meta or {}).get("downloaded_at"))
                        item.warnings.append(
                            f"{exc.message} Dernier fichier local réutilisé : aucune "
                            "donnée n'est inventée, mais il peut manquer la journée la "
                            "plus récente."
                        )
                else:
                    item.status = "failed"
                    item.error = exc.message
            else:
                try:
                    item.sha256, item.size_bytes = _store(
                        division, contenu, len(rows), moment
                    )
                except OSError as exc:
                    item.warnings.append(
                        f"Fichier non conservé sur le disque ({type(exc).__name__}) : "
                        "il sera retéléchargé à la passe suivante."
                    )
                item.rows = len(rows)
                item.downloaded_at = moment

        if contenu is not None:
            fichier, _ = _paths(division)
            item.path = str(fichier)
            item.size_bytes = item.size_bytes or len(contenu)
            if item.status == "skipped":
                item.status = "applied"
        prepared.append(
            _Prepared(report=item, competition=competition, season=season, rows=rows)
        )
    return prepared


def _parse_moment(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def download(
    db: Session,
    *,
    leagues: list[str] | None = None,
    now: datetime | None = None,
    client: Any | None = None,
) -> CsvDownloadReport:
    """Télécharge les fichiers et les conserve, sans écrire dans les rencontres."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    report = CsvDownloadReport(directory=str(storage_dir()))
    selected = _selected(leagues)
    if not selected:
        report.status = "empty"
        return report

    own_client = client is None
    connector = client
    try:
        if connector is None:
            connector = make_client()
        prepared = _prepare_files(db, connector, selected, moment, refresh=True)
    finally:
        if own_client and connector is not None:
            connector.close()

    report.files = [item.report for item in prepared]
    statuts = [item.status for item in report.files]
    if all(statut == "failed" for statut in statuts):
        report.status = "failed"
    elif any(statut != "applied" for statut in statuts):
        report.status = "partial"
    report.error = next((item.error or "" for item in report.files if item.error), None)
    _record_run(
        db,
        action="download",
        status=report.status,
        moment=moment,
        params={"leagues": selected, "directory": report.directory},
        summary={
            **report.totals,
            "leagues": [item.as_dict() for item in report.files],
        },
        error=report.error,
    )
    return report


def run(
    db: Session,
    *,
    leagues: list[str] | None = None,
    refresh: bool = True,
    now: datetime | None = None,
    client: Any | None = None,
) -> CsvReport:
    """Enrichit les rencontres terminées : xG et cotes de clôture.

    Ne valide pas la transaction : la route commite, comme pour les autres
    passes.
    """
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    report = CsvReport(directory=str(storage_dir()))
    selected = _selected(leagues)
    if not selected:
        report.status = "empty"
        return report

    own_client = client is None
    connector = client
    try:
        if connector is None:
            connector = make_client()
        prepared = _prepare_files(db, connector, selected, moment, refresh=refresh)
        report.files = [item.report for item in prepared]

        for entry in prepared:
            league = CsvLeagueReport(
                code=entry.report.code,
                division=entry.report.division,
                name=entry.report.name,
            )
            if entry.season is None or entry.competition is None:
                league.status = "failed"
                league.error = entry.report.error
            else:
                try:
                    _run_league(db, league, entry, moment)
                except ConnectorError as exc:
                    league.status = "failed"
                    league.error = exc.message
            report.leagues.append(league)
    finally:
        if own_client and connector is not None:
            connector.close()

    statuts = [item.status for item in report.leagues]
    if all(statut == "failed" for statut in statuts):
        report.status = "failed"
    elif any(statut != "applied" for statut in statuts) or any(
        item.status != "applied" for item in report.files
    ):
        report.status = "partial"
    elif sum(item.rows for item in report.leagues) == 0:
        report.status = "empty"
    report.error = next(
        (item.error or "" for item in report.leagues if item.error), None
    )
    _record_run(
        db,
        action="import",
        status=report.status,
        moment=moment,
        params={
            "leagues": selected,
            "directory": report.directory,
            "refresh": refresh,
        },
        summary={
            **report.totals,
            "files": [item.as_dict() for item in report.files],
        },
        error=report.error,
    )
    return report


def _run_league(
    db: Session,
    league: CsvLeagueReport,
    entry: _Prepared,
    moment: datetime,
) -> None:
    """Apparie et écrit une compétition ; aucune écriture en cas de doute."""
    season = entry.season
    assert season is not None  # garanti par l'appelant
    rows = entry.rows
    league.rows = len(rows)
    if not rows:
        league.status = "empty"
        league.warnings.append("Le fichier ne contient aucune rencontre jouée.")
        return

    candidates = _candidates(db, season.id)
    if not candidates:
        league.status = "empty"
        league.warnings.append(
            "Aucune rencontre terminée en base pour cette saison : importez d'abord "
            "les faits."
        )
        return

    links = _link_index(db, rows)
    claimed = {
        link.match_id: link.row_key
        for link in db.scalars(
            select(CsvLink).where(
                CsvLink.source == SOURCE,
                CsvLink.season_id == season.id,
                CsvLink.status == "applied",
            )
        ).all()
        if link.match_id is not None
    }

    seen: set[str] = set()
    for row in rows:
        key = row.row_key
        if key in seen:
            league.warnings.append(
                f"Ligne en double ignorée dans le fichier : {row.label} ({row.played_on})."
            )
            continue
        seen.add(key)
        link = links.get(key)
        if link is not None and link.status == "ignored":
            league.ignored += 1
            continue

        if link is not None and link.status == "applied" and link.match_id is not None:
            league.links_reused += 1
            league.matched += 1
            _write_row(db, row, link.match_id, league)
            continue

        decision = decide_row(row, candidates)
        if decision.reason == "matched" and decision.match_id is not None:
            match_id = decision.match_id
            other = claimed.get(match_id)
            if other is not None and other != key:
                league.ambiguous += 1
                _save_link(
                    db,
                    entry,
                    row,
                    status="pending",
                    decision=decision,
                    match_id=None,
                    moment=moment,
                    note=(
                        "Une autre ligne enrichit déjà cette rencontre : décision "
                        "manuelle nécessaire."
                    ),
                    player=link,
                )
                continue
            claimed[match_id] = key
            league.matched += 1
            if link is None:
                league.links_created += 1
            else:
                league.links_reused += 1
            _save_link(
                db,
                entry,
                row,
                status="applied",
                decision=decision,
                match_id=match_id,
                moment=moment,
                player=link,
            )
            _write_row(db, row, match_id, league)
            continue

        if decision.reason == "ambiguous":
            league.ambiguous += 1
        else:
            league.unmatched += 1
        _save_link(
            db,
            entry,
            row,
            status="pending",
            decision=decision,
            match_id=None,
            moment=moment,
            player=link,
        )

    if league.ambiguous:
        league.warnings.append(
            f"{league.ambiguous} ligne(s) ambiguë(s) : aucune écriture, la décision "
            "est enregistrée et sera reposée à la passe suivante."
        )
    if league.unmatched:
        league.warnings.append(
            f"{league.unmatched} ligne(s) sans rencontre correspondante : ignorée(s)."
        )
    if league.manual_kept:
        league.warnings.append(
            f"{league.manual_kept} marché(s) saisi(s) à la main conservé(s) tel(s) quel(s)."
        )
    if league.odds_missing:
        league.warnings.append(
            f"{league.odds_missing} rencontre(s) sans cotes de clôture complètes : "
            "aucune cote inventée."
        )


def _candidates(db: Session, season_id: UUID) -> list[CsvCandidate]:
    """Rencontres terminées importées du fournisseur de faits.

    Une rencontre saisie à la main (`external_id` nul) n'est jamais candidate :
    elle reste hors de portée d'un import.
    """
    rows = db.scalars(
        select(Match)
        .options(selectinload(Match.home_team), selectinload(Match.away_team))
        .where(
            Match.season_id == season_id,
            Match.status == MatchStatus.TERMINE,
            Match.external_id.is_not(None),
        )
    ).all()
    return [
        CsvCandidate(
            match_id=row.id,
            played_on=as_utc(row.kickoff_at).date(),
            home_name=row.home_team.name,
            away_name=row.away_team.name,
            home_score=row.home_score,
            away_score=row.away_score,
            half_time_home=row.half_time_home_score,
            half_time_away=row.half_time_away_score,
        )
        for row in rows
    ]


def _link_index(db: Session, rows: list[CsvRow]) -> dict[str, CsvLink]:
    keys = [row.row_key for row in rows]
    if not keys:
        return {}
    result = db.scalars(
        select(CsvLink).where(CsvLink.source == SOURCE, CsvLink.row_key.in_(keys))
    ).all()
    return {link.row_key: link for link in result}


def _save_link(
    db: Session,
    entry: _Prepared,
    row: CsvRow,
    *,
    status: str,
    decision: CsvDecision,
    match_id: UUID | None,
    moment: datetime,
    player: CsvLink | None = None,
    note: str | None = None,
) -> CsvLink:
    """Enregistre la décision. Une ligne appliquée n'est jamais reposée."""
    season = entry.season
    assert season is not None  # garanti par l'appelant
    link = player
    if link is None:
        link = CsvLink(
            source=SOURCE,
            season_id=season.id,
            row_key=row.row_key,
            row_date=row.played_on,
            home_team_name=row.home_name[:120],
            away_team_name=row.away_name[:120],
            home_score=row.home_score,
            away_score=row.away_score,
            half_time_home_score=row.half_time_home,
            half_time_away_score=row.half_time_away,
        )
        db.add(link)
    link.match_id = match_id
    link.status = status
    link.method = "score" if status == "applied" else None
    link.confidence = decision.confidence if decision.confidence else None
    link.margin = decision.margin if decision.margin else None
    link.decided_at = moment
    link.decided_by = "import"
    link.note = (note or decision.note or "")[:500] or None
    db.flush()
    return link


def _write_row(
    db: Session,
    row: CsvRow,
    match_id: UUID,
    league: CsvLeagueReport,
) -> None:
    """Écrit le xG et les cotes de clôture d'une ligne déjà rattachée."""
    match = db.scalar(
        select(Match)
        .options(selectinload(Match.home_team), selectinload(Match.away_team))
        .where(Match.id == match_id)
    )
    if match is None:
        return
    _write_xg(db, match, row, league)
    _write_closing(db, match, row, league)


def _write_xg(
    db: Session,
    match: Match,
    row: CsvRow,
    league: CsvLeagueReport,
) -> None:
    """Écrit le xG absent, conserve le xG déjà connu.

    Le xG d'origine est tracé dans `extra["xg_source"]`, sans écraser les autres
    clés : la provenance reste lisible même si le fournisseur de faits publie
    un jour son propre xG.
    """
    for ligne, equipe in (
        (row.home_stats, match.home_team),
        (row.away_stats, match.away_team),
    ):
        if ligne.expected_goals is None:
            continue
        existant = db.scalar(
            select(TeamMatchStats).where(
                TeamMatchStats.match_id == match.id,
                TeamMatchStats.team_id == equipe.id,
            )
        )
        if existant is None:
            db.add(
                TeamMatchStats(
                    match_id=match.id,
                    team_id=equipe.id,
                    is_home=ligne.is_home,
                    goals_for=ligne.goals_for,
                    goals_against=ligne.goals_against,
                    expected_goals=ligne.expected_goals,
                    extra={"xg_source": SOURCE},
                    data_source=SOURCE,
                )
            )
            league.stats_created += 1
            continue
        if existant.expected_goals is not None:
            league.xg_kept += 1
            continue
        existant.expected_goals = ligne.expected_goals
        extra = dict(existant.extra or {})
        extra.setdefault("xg_source", SOURCE)
        existant.extra = extra
        league.xg_written += 1
    db.flush()


def _write_closing(
    db: Session,
    match: Match,
    row: CsvRow,
    league: CsvLeagueReport,
) -> None:
    """Enregistre la moyenne du marché à la clôture, jamais une cote dérivée."""
    closing: ClosingOdds | None = row.closing
    if closing is None:
        league.odds_missing += 1
        return
    captured_at = as_utc(match.kickoff_at)
    marches: list[tuple[str, float | None, dict[str, float]]] = [
        (RESULT_TEMPLATE, None, closing.result_1x2)
    ]
    total = closing.total_2_5
    if total is not None:
        marches.append((TOTAL_TEMPLATE, TOTAL_LINE, total))
    for template_code, line, outcomes in marches:
        _write_market(db, match, template_code, line, outcomes, captured_at, league)


def _write_market(
    db: Session,
    match: Match,
    template_code: str,
    line: float | None,
    outcomes: dict[str, float],
    captured_at: datetime,
    league: CsvLeagueReport,
) -> None:
    template = resolve_template(db, template_code)
    if template is None:
        league.warnings.append(
            f"Modèle de marché absent du catalogue : {template_code}."
        )
        return

    signature = build_signature(
        template_code=template_code,
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
        select(Market).where(Market.match_id == match.id, Market.signature == signature)
    )
    if market is not None and market.is_custom:
        league.manual_kept += 1
        return
    if market is None:
        market = Market(
            match_id=match.id,
            template_code=template_code,
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
        league.markets_written += 1

    selections = {selection.code: selection for selection in market.selections}
    for code, price in outcomes.items():
        selection = selections.get(code)
        if selection is None:
            league.warnings.append(
                f"Issue hors catalogue ignorée pour {template_code} : {code}."
            )
            continue
        if _snapshot_exists(db, selection.id, captured_at):
            continue
        db.add(
            OddsSnapshot(
                selection_id=selection.id,
                decimal_odds=price,
                captured_at=captured_at,
                bookmaker=BOOKMAKER_LABEL,
                source=SOURCE,
            )
        )
        league.snapshots_written += 1
    db.flush()


def _snapshot_exists(db: Session, selection_id: UUID, captured_at: datetime) -> bool:
    moment = as_utc(captured_at)
    rows = db.scalars(
        select(OddsSnapshot).where(
            OddsSnapshot.selection_id == selection_id,
            OddsSnapshot.source == SOURCE,
        )
    ).all()
    return any(as_utc(item.captured_at) == moment for item in rows)


def _json_safe(value: Any) -> Any:
    """Rend un rapport sérialisable dans le journal JSON (dates en texte ISO)."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _record_run(
    db: Session,
    *,
    action: str,
    status: str,
    moment: datetime,
    params: dict[str, Any],
    summary: dict[str, Any],
    error: str | None,
) -> None:
    if status in {"applied", "empty"}:
        code = SyncStatus.APPLIED.value
    elif status == "partial":
        code = SyncStatus.PARTIAL.value
    else:
        code = SyncStatus.FAILED.value
    db.add(
        SyncRun(
            provider=PROVIDER,
            operation=SyncOperation.CSV.value,
            status=code,
            params=_json_safe({"action": action, **params}),
            summary=_json_safe(summary),
            requests_used=summary.get("files", 0) if action == "download" else 0,
            credits_used=0,
            quota_remaining=None,
            error_message=(error or "")[:1000] or None,
            applied_at=moment,
        )
    )
    db.flush()


def overview(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """État de la source CSV pour la page Synchronisation."""
    del now  # l'état est calculé sur la base et le disque, sans horloge de passe
    directory = storage_dir()
    files: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []

    for code in TRACKED_LEAGUES:
        division = DIVISIONS[code]
        meta = _read_sidecar(division) or {}
        fichier, _ = _paths(division)
        stored = fichier.exists()
        rows = int(meta.get("rows") or 0)
        fiche = _season(db, code)
        name = division_label(division)
        season_label = fiche[1].label if fiche else None
        files.append(
            {
                "code": code,
                "division": division,
                "name": name,
                "season_label": season_label,
                "stored": stored,
                "path": str(fichier) if stored else None,
                "sha256": meta.get("sha256"),
                "size_bytes": int(meta.get("size_bytes") or 0)
                if stored
                else 0,
                "rows": rows,
                "downloaded_at": _parse_moment(meta.get("downloaded_at")),
            }
        )
        if fiche is None:
            coverage.append(
                {
                    "code": code,
                    "division": division,
                    "name": name,
                    "season_label": None,
                    "finished": 0,
                    "covered": 0,
                    "links_applied": 0,
                }
            )
            continue
        _competition, season = fiche
        finished = (
            db.scalar(
                select(func.count())
                .select_from(Match)
                .where(
                    Match.season_id == season.id,
                    Match.status == MatchStatus.TERMINE,
                )
            )
            or 0
        )
        covered = (
            db.scalar(
                select(func.count(func.distinct(Match.id)))
                .select_from(Match)
                .join(TeamMatchStats, TeamMatchStats.match_id == Match.id)
                .where(
                    Match.season_id == season.id,
                    TeamMatchStats.expected_goals.is_not(None),
                )
            )
            or 0
        )
        applied = (
            db.scalar(
                select(func.count())
                .select_from(CsvLink)
                .where(
                    CsvLink.source == SOURCE,
                    CsvLink.season_id == season.id,
                    CsvLink.status == "applied",
                )
            )
            or 0
        )
        coverage.append(
            {
                "code": code,
                "division": division,
                "name": name,
                "season_label": season_label,
                "finished": int(finished),
                "covered": int(covered),
                "links_applied": int(applied),
            }
        )

    for item in files:
        if not item["stored"]:
            # Le fichier a disparu du disque : les compteurs sont remis à zéro.
            item["rows"] = 0
    total_rows = sum(int(item["rows"]) for item in files)

    xg_rows = (
        db.scalar(
            select(func.count())
            .select_from(TeamMatchStats)
            .where(TeamMatchStats.expected_goals.is_not(None))
        )
        or 0
    )
    links_applied = (
        db.scalar(
            select(func.count())
            .select_from(CsvLink)
            .where(CsvLink.source == SOURCE, CsvLink.status == "applied")
        )
        or 0
    )
    links_pending = (
        db.scalar(
            select(func.count())
            .select_from(CsvLink)
            .where(CsvLink.source == SOURCE, CsvLink.status == "pending")
        )
        or 0
    )
    closing_markets = (
        db.scalar(
            select(func.count(func.distinct(Market.id)))
            .select_from(Market)
            .join(Selection, Selection.market_id == Market.id)
            .join(OddsSnapshot, OddsSnapshot.selection_id == Selection.id)
            .where(OddsSnapshot.source == SOURCE)
        )
        or 0
    )
    closing_rows = (
        db.scalar(
            select(func.count())
            .select_from(OddsSnapshot)
            .where(OddsSnapshot.source == SOURCE)
        )
        or 0
    )
    covered_matches = (
        db.scalar(
            select(func.count(func.distinct(Match.id)))
            .select_from(Match)
            .join(TeamMatchStats, TeamMatchStats.match_id == Match.id)
            .where(TeamMatchStats.expected_goals.is_not(None))
        )
        or 0
    )

    pending_rows = db.execute(
        select(CsvLink, Season, Competition)
        .join(Season, Season.id == CsvLink.season_id)
        .join(Competition, Competition.id == Season.competition_id)
        .where(CsvLink.source == SOURCE, CsvLink.status == "pending")
        .order_by(CsvLink.row_date.desc(), CsvLink.home_team_name)
        .limit(20)
    ).all()
    pending = [
        {
            "row_key": link.row_key,
            "competition": competition.name,
            "played_on": link.row_date,
            "label": f"{link.home_team_name} — {link.away_team_name}",
            "confidence": float(link.confidence) if link.confidence is not None else None,
            "margin": float(link.margin) if link.margin is not None else None,
            "note": link.note,
        }
        for link, _season_row, competition in pending_rows
    ]

    last_run = db.scalar(
        select(SyncRun)
        .where(
            SyncRun.provider == PROVIDER,
            SyncRun.operation == SyncOperation.CSV.value,
        )
        .order_by(SyncRun.created_at.desc())
        .limit(1)
    )
    return {
        "provider": PROVIDER,
        "configured": True,
        "directory": str(directory),
        "season": files[0]["season_label"] if files else None,
        "files": files,
        "totals": {
            "files": sum(1 for item in files if item["stored"]),
            "rows": total_rows,
            "matches_covered": int(covered_matches),
            "xg_rows": int(xg_rows),
            "links_applied": int(links_applied),
            "links_pending": int(links_pending),
            "closing_markets": int(closing_markets),
            "closing_rows": int(closing_rows),
        },
        "coverage": coverage,
        "pending": pending,
        "last_run": last_run,
    }
