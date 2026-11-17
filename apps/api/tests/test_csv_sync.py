"""Tests de l'enrichissement CSV : xG et cotes de clôture (phase 15 étape 5).

Deux niveaux, comme pour les cotes :

* le **matcher** est pur : la rencontre est identifiée par son résultat
  (date, score final, mi-temps), le nom ne confirme que le sens
  domicile/extérieur ;
* le **service** reçoit un client factice : aucun appel réseau n'est effectué,
  et les fichiers sont écrits dans un dossier temporaire, jamais dans
  `data/local/csv`.

Les deux fixtures `F1-2627-extract.csv` et `SP1-2627-extract.csv` sont des
extraits **réels** des fichiers publics 2026-27 : elles prouvent que les noms
de colonnes (`AvgCH`, `AvgCD`, `AvgCA`, `AvgC>2.5`, `AvgC<2.5`, `HxG`, `AxG`)
sont bien ceux du fournisseur.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from app.connectors.base import ProviderPayloadError
from app.connectors.csv_matching import (
    CsvCandidate,
    decide_row,
    orientation_confidence,
)
from app.connectors.football_data_uk.client import FootballDataUkClient
from app.connectors.football_data_uk.csvar import decode_bytes
from app.connectors.football_data_uk.mapping import CsvRow, parse_rows
from app.connectors.http import HttpClient
from app.core.config import settings
from app.models.connector import SyncRun
from app.models.link import CsvLink
from app.models.market import Market, OddsSnapshot, Selection
from app.models.match import Match, MatchStatus, TeamMatchStats
from app.models.reference import Competition, Season, Team
from app.services import csv_sync
from app.services.markets import build_signature, resolve_template
from sqlalchemy import func, select
from sqlalchemy.orm import Session

FIXTURES = Path(__file__).parent / "fixtures" / "csv"
MOMENT = datetime(2026, 11, 17, 8, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 11, 8, 20, 0, tzinfo=UTC)

HEADER = (
    "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HTHG,HTAG,HxG,AxG,"
    "AvgCH,AvgCD,AvgCA,AvgC>2.5,AvgC<2.5"
)


def _fixture(name: str) -> list[CsvRow]:
    contenu = (FIXTURES / name).read_bytes()
    return parse_rows(decode_bytes(contenu), division=name.split("-")[0])


def _row(rows: list[CsvRow], home: str, away: str) -> CsvRow:
    for row in rows:
        if row.home_name == home and row.away_name == away:
            return row
    raise AssertionError(f"Ligne absente de la fixture : {home} - {away}")


def _csv(rows: list[str]) -> bytes:
    return ("\n".join([HEADER, *rows]) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Lecture des fichiers réels
# ---------------------------------------------------------------------------


def test_real_f1_fixture_parses_xg_and_closing_odds() -> None:
    """Le fichier 2026-27 publie le xG et la clôture moyenne (`AvgC*`)."""
    rows = _fixture("F1-2627-extract.csv")
    assert len(rows) == 10
    assert all(row.closing is not None for row in rows)
    assert all(row.home_stats.expected_goals is not None for row in rows)
    assert all(row.away_stats.expected_goals is not None for row in rows)

    rennes = _row(rows, "Rennes", "Lille")
    assert rennes.played_on == date(2026, 11, 8)
    assert (rennes.home_score, rennes.away_score) == (1, 2)
    assert (rennes.half_time_home, rennes.half_time_away) == (1, 1)
    assert rennes.home_stats.expected_goals == pytest.approx(1.53)
    assert rennes.away_stats.expected_goals == pytest.approx(0.36)
    closing = rennes.closing
    assert closing is not None
    assert (closing.home, closing.draw, closing.away) == pytest.approx(
        (2.32, 3.28, 3.06)
    )
    assert closing.total_2_5 == pytest.approx({"plus": 1.89, "moins": 1.85})
    assert closing.result_1x2 == pytest.approx({"1": 2.32, "X": 3.28, "2": 3.06})
    # La clé porte le résultat et les noms : deux rencontres distinctes peuvent
    # partager le même score le même jour, mais pas les mêmes équipes.
    assert rennes.row_key == "F1|2026-11-08|1-2|1-1|rennes|lille"


def test_real_sp1_fixture_parses_xg_and_closing_odds() -> None:
    rows = _fixture("SP1-2627-extract.csv")
    assert len(rows) == 6
    valencia = _row(rows, "Valencia", "Real Madrid")
    assert (valencia.home_score, valencia.away_score) == (0, 3)
    assert valencia.home_stats.expected_goals == pytest.approx(0.18)
    assert valencia.away_stats.expected_goals == pytest.approx(2.34)
    assert valencia.closing is not None
    assert valencia.closing.home == pytest.approx(10.84)


def test_client_fetches_bytes_and_rows(monkeypatch) -> None:
    """`fetch_file` renvoie le contenu brut (empreinte) et les rencontres."""
    contenu = (FIXTURES / "F1-2627-extract.csv").read_bytes()
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, content=contenu)

    with HttpClient(transport=httpx.MockTransport(handler)) as http:
        client = FootballDataUkClient(
            base_url="https://football-data.co.uk", http=http
        )
        brut, rows = client.fetch_file(division="F1", season="2026-2027")

    assert brut == contenu
    assert len(rows) == 10
    assert urls == ["https://football-data.co.uk/mmz4281/2627/F1.csv"]


# ---------------------------------------------------------------------------
# Matcher pur
# ---------------------------------------------------------------------------


def _candidate(
    value: int,
    *,
    home: str,
    away: str,
    played_on: date = date(2026, 11, 8),
    score: tuple[int, int] = (1, 2),
    half_time: tuple[int | None, int | None] = (1, 1),
) -> CsvCandidate:
    return CsvCandidate(
        match_id=UUID(int=value),
        played_on=played_on,
        home_name=home,
        away_name=away,
        home_score=score[0],
        away_score=score[1],
        half_time_home=half_time[0],
        half_time_away=half_time[1],
    )


def test_result_key_matches_even_when_the_name_is_abbreviated() -> None:
    """`Rennes` côté CSV, `Stade Rennais` en base : le résultat tranche."""
    row = _row(_fixture("F1-2627-extract.csv"), "Rennes", "Lille")
    candidats = [
        _candidate(1, home="Stade Rennais", away="Lille"),
        # Même jour, même score, autre match : le nom écarte ce candidat.
        _candidate(2, home="Lens", away="Marseille"),
    ]
    decision = decide_row(row, candidats)
    assert decision.matched
    assert decision.match_id == UUID(int=1)
    assert decision.reason == "matched"
    assert decision.confidence >= 0.60
    assert decision.margin >= 0.25


def test_orientation_confidence_refuses_reversed_sides() -> None:
    """Une ligne dont les noms vont mieux à l'envers ne vaut jamais « presque »."""
    row = _row(_fixture("F1-2627-extract.csv"), "Rennes", "Lille")
    inversee = _candidate(1, home="Lille", away="Stade Rennais")
    assert orientation_confidence(row, inversee) == 0.0
    decision = decide_row(row, [inversee])
    assert not decision.matched
    assert decision.reason == "unmatched"


def test_ambiguous_score_is_not_written() -> None:
    """Deux rencontres au même score, noms également proches : rien n'est écrit."""
    row = _row(_fixture("F1-2627-extract.csv"), "Rennes", "Lille")
    candidats = [
        _candidate(1, home="Stade Rennais", away="Lille"),
        _candidate(2, home="Stade Rennais", away="Lille OSC"),
    ]
    decision = decide_row(row, candidats)
    assert not decision.matched
    assert decision.reason == "ambiguous"
    assert decision.margin < 0.25
    assert decision.note is not None


def _single_row(home: str, away: str) -> CsvRow:
    rows = parse_rows(
        decode_bytes(
            _csv([f"F1,08/11/2026,{home},{away},1,2,1,1,1.5,0.4,2.3,3.3,3.1,1.9,1.9"])
        ),
        division="F1",
    )
    assert len(rows) == 1
    return rows[0]


def test_unique_result_candidate_accepts_an_exonym() -> None:
    """`Paris SG` / `Paris Saint-Germain` : le résultat désigne la rencontre."""
    row = _single_row("Paris SG", "Lille")
    candidat = _candidate(1, home="Paris Saint-Germain", away="Lille")
    assert orientation_confidence(row, candidat) < 0.60
    decision = decide_row(row, [candidat])
    assert decision.matched
    assert decision.match_id == UUID(int=1)
    assert decision.margin == 1.0
    assert decision.note is not None and "exonyme" in decision.note


def test_unique_result_candidate_with_reversed_names_is_refused() -> None:
    """Même unique, un candidat dont les noms sont inversés n'est pas retenu."""
    row = _single_row("Paris SG", "Lille")
    inverse = _candidate(1, home="Lille", away="Paris Saint-Germain")
    assert not decide_row(row, [inverse]).matched


def test_two_candidates_need_a_confirming_name() -> None:
    """À deux candidats, un exonyme sous le seuil ne suffit pas : rien n'est écrit."""
    row = _single_row("Paris SG", "Lille")
    decision = decide_row(
        row,
        [
            _candidate(1, home="Paris Saint-Germain", away="Lille"),
            _candidate(2, home="Lens", away="Marseille"),
        ],
    )
    assert not decision.matched
    assert decision.reason == "unmatched"


def test_different_score_or_date_is_unmatched() -> None:
    row = _row(_fixture("F1-2627-extract.csv"), "Rennes", "Lille")
    autre_score = _candidate(1, home="Stade Rennais", away="Lille", score=(2, 1))
    autre_date = _candidate(
        2, home="Stade Rennais", away="Lille", played_on=date(2026, 11, 9)
    )
    assert decide_row(row, [autre_score]).reason == "unmatched"
    assert decide_row(row, [autre_date]).reason == "unmatched"
    assert decide_row(row, []).reason == "unmatched"


def test_unknown_half_time_does_not_disqualify() -> None:
    """Une mi-temps inconnue d'un côté ne peut pas contredire le résultat."""
    row = _row(_fixture("F1-2627-extract.csv"), "Rennes", "Lille")
    decision = decide_row(
        row,
        [_candidate(1, home="Stade Rennais", away="Lille", half_time=(None, None))],
    )
    assert decision.matched


def test_same_result_but_different_teams_are_two_distinct_rows() -> None:
    """Deux rencontres 1-2 (mi-temps 1-1) le même jour restent deux lignes."""
    rows = parse_rows(
        decode_bytes(
            _csv(
                [
                    "F1,08/11/2026,Rennes,Lille,1,2,1,1,1.5,0.4,2.32,3.28,3.06,1.89,1.85",
                    "F1,08/11/2026,Lens,Marseille,1,2,1,1,1.7,0.8,2.4,3.4,2.9,1.8,2.0",
                ]
            )
        ),
        division="F1",
    )
    assert len({row.row_key for row in rows}) == 2


# ---------------------------------------------------------------------------
# Service : monde de test et client factice
# ---------------------------------------------------------------------------


def _team(db: Session, sport_id: Any, name: str, external_id: str | None) -> Team:
    team = Team(sport_id=sport_id, name=name, external_id=external_id)
    db.add(team)
    db.flush()
    return team


def _match(
    db: Session,
    season_id: Any,
    home: Team,
    away: Team,
    *,
    kickoff: datetime,
    external_id: str | None,
    score: tuple[int, int] | None = (1, 2),
    half_time: tuple[int, int] | None = (1, 1),
) -> Match:
    match = Match(
        season_id=season_id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_at=kickoff,
        status=MatchStatus.TERMINE if score else MatchStatus.PROGRAMME,
        external_id=external_id,
        data_source="bigballsdata" if external_id else "manual",
        home_score=score[0] if score else None,
        away_score=score[1] if score else None,
        half_time_home_score=half_time[0] if half_time else None,
        half_time_away_score=half_time[1] if half_time else None,
    )
    db.add(match)
    db.flush()
    return match


def _world(db: Session) -> dict[str, Any]:
    """Une compétition `ligue1`, deux rencontres du fournisseur, une manuelle."""
    from app.models.reference import Sport

    football = db.scalar(select(Sport).where(Sport.code == "football"))
    assert football is not None
    competition = Competition(
        sport_id=football.id, name="Ligue 1", code="ligue1", country="France", tier=1
    )
    db.add(competition)
    db.flush()
    season = Season(
        competition_id=competition.id,
        label="2026-2027",
        is_current=True,
        start_date=date(2026, 8, 1),
    )
    db.add(season)
    db.flush()

    rennes = _team(db, football.id, "Stade Rennais", "t-rennes")
    lille = _team(db, football.id, "Lille", "t-lille")
    angers = _team(db, football.id, "Angers", "t-angers")
    nice = _team(db, football.id, "Nice", "t-nice")
    lens = _team(db, football.id, "Lens", "t-lens")

    matches = {
        "rennes": _match(
            db,
            season.id,
            rennes,
            lille,
            kickoff=KICKOFF,
            external_id="m-rennes",
        ),
        "angers": _match(
            db,
            season.id,
            angers,
            nice,
            kickoff=KICKOFF - timedelta(hours=2),
            external_id="m-angers",
            score=(0, 2),
            half_time=(0, 1),
        ),
        # Rencontre saisie à la main : jamais candidate à un import.
        "manuel": _match(
            db,
            season.id,
            lens,
            rennes,
            kickoff=KICKOFF + timedelta(minutes=45),
            external_id=None,
        ),
    }
    ids = {
        "competition_id": competition.id,
        "season_id": season.id,
        "teams": {
            "rennes": rennes.id,
            "lille": lille.id,
            "angers": angers.id,
            "nice": nice.id,
            "lens": lens.id,
        },
        "matches": {name: match.id for name, match in matches.items()},
    }
    db.commit()
    return ids


class FakeCsvClient:
    """Client football-data.co.uk simulé : aucun appel réseau."""

    provider = "football_data_uk"

    def __init__(self, files: dict[str, bytes], *, failing: set[str] | None = None) -> None:
        self.files = files
        self.failing = failing or set()
        self.calls: list[tuple[str, str]] = []

    def fetch_file(self, *, division: str, season: str) -> tuple[bytes, list[CsvRow]]:
        self.calls.append((division, season))
        if division in self.failing:
            raise ProviderPayloadError("Le fournisseur est injoignable (test).")
        contenu = self.files[division]
        return contenu, parse_rows(decode_bytes(contenu), division=division)

    def close(self) -> None:  # pragma: no cover - un client fourni n'est pas fermé
        raise AssertionError("Le client fourni ne doit pas être fermé.")


class OfflineClient:
    """Client qui échoue si on lui demande le réseau."""

    provider = "football_data_uk"

    def fetch_file(self, *, division: str, season: str) -> tuple[bytes, list[CsvRow]]:
        raise AssertionError(
            "Aucun appel réseau ne doit être fait quand un fichier local existe."
        )


def _f1_csv() -> bytes:
    return _csv(
        [
            # Deux rencontres réelles de la base.
            "F1,08/11/2026,Rennes,Lille,1,2,1,1,1.53,0.36,3.3,3.25,2.38,1.6,2.25",
            "F1,08/11/2026,Angers,Nice,0,2,0,1,0.85,2.13,3.8,1.83,4.1,1.65,2.2",
            # Aucune rencontre de la base à cette date : ligne en attente.
            "F1,07/11/2026,Troyes,Le Mans,2,0,1,0,2.02,0.2,3.3,3.2,2.35,1.7,2.1",
        ]
    )


@pytest.fixture()
def storage(tmp_path, monkeypatch) -> Path:
    """Les fichiers de test ne sortent jamais du dossier temporaire."""
    dossier = tmp_path / "csv"
    monkeypatch.setattr(settings, "csv_storage_dir", str(dossier))
    return dossier


@pytest.fixture()
def world(engine, seeded: None) -> dict[str, Any]:
    with Session(engine) as db:
        return _world(db)


def _run(db: Session, client: Any, **options: Any) -> Any:
    return csv_sync.run(db, leagues=["ligue1"], now=MOMENT, client=client, **options)


def _download(db: Session, client: Any) -> Any:
    return csv_sync.download(db, leagues=["ligue1"], now=MOMENT, client=client)


def _stats(db: Session, match_id: Any, team_id: Any) -> TeamMatchStats | None:
    return db.scalar(
        select(TeamMatchStats).where(
            TeamMatchStats.match_id == match_id,
            TeamMatchStats.team_id == team_id,
        )
    )


def _snapshots(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(OddsSnapshot)) or 0


# ---------------------------------------------------------------------------
# Écriture du xG et des cotes de clôture
# ---------------------------------------------------------------------------


def test_run_writes_xg_and_closing_odds(world, engine, storage) -> None:
    client = FakeCsvClient({"F1": _f1_csv()})
    with Session(engine) as db:
        report = _run(db, client)
        db.commit()

        assert report.status == "applied"
        assert client.calls == [("F1", "2026-2027")]
        league = report.leagues[0]
        assert (league.rows, league.matched, league.unmatched) == (3, 2, 1)
        assert league.links_created == 2
        assert league.odds_missing == 0

        rennes = world["matches"]["rennes"]
        domicile = _stats(db, rennes, world["teams"]["rennes"])
        exterieur = _stats(db, rennes, world["teams"]["lille"])
        assert domicile is not None and exterieur is not None
        assert domicile.expected_goals == pytest.approx(1.53)
        assert exterieur.expected_goals == pytest.approx(0.36)
        assert domicile.extra == {"xg_source": "csv"}
        assert domicile.data_source == "csv"

        marches = db.scalars(select(Market).where(Market.match_id == rennes)).all()
        assert {market.template_code for market in marches} == {
            "football.resultat_1x2",
            "football.total_buts",
        }
        resultat = next(
            market for market in marches if market.template_code == "football.resultat_1x2"
        )
        assert resultat.is_custom is False
        assert resultat.notes == "csv"
        assert {selection.code for selection in resultat.selections} == {"1", "X", "2"}
        snapshots = db.scalars(
            select(OddsSnapshot).where(
                OddsSnapshot.selection_id.in_(
                    [selection.id for selection in resultat.selections]
                )
            )
        ).all()
        assert {row.bookmaker for row in snapshots} == {"Clôture (moyenne)"}
        assert {row.source for row in snapshots} == {"csv"}
        assert {round(row.decimal_odds, 2) for row in snapshots} == {3.3, 3.25, 2.38}
        # Relevé daté du coup d'envoi : c'est bien une clôture, pas une cote du jour.
        kickoff = KICKOFF
        assert all(
            row.captured_at.replace(tzinfo=UTC) == kickoff for row in snapshots
        )

        total = next(
            market for market in marches if market.template_code == "football.total_buts"
        )
        assert total.line == 2.5
        assert {selection.code for selection in total.selections} == {"plus", "moins"}

        # La rencontre manuelle (sans identifiant) n'a jamais été touchée.
        manuel = world["matches"]["manuel"]
        assert db.scalar(select(func.count()).select_from(Market).where(
            Market.match_id == manuel
        )) == 0


def test_run_records_a_journal_entry(world, engine, storage) -> None:
    client = FakeCsvClient({"F1": _f1_csv()})
    with Session(engine) as db:
        _run(db, client)
        db.commit()
        run = db.scalar(select(SyncRun))
        assert run is not None
        assert run.provider == "football_data_uk"
        assert run.operation == "csv"
        assert run.status == "applied"
        assert run.params["action"] == "import"
        assert run.params["leagues"] == ["ligue1"]
        assert run.summary["matched"] == 2
        assert run.credits_used == 0
        assert run.quota_remaining is None


def test_second_run_writes_nothing_new(world, engine, storage) -> None:
    client = FakeCsvClient({"F1": _f1_csv()})
    with Session(engine) as db:
        _run(db, client)
        db.commit()
        marches = db.scalar(select(func.count()).select_from(Market)) or 0
        relevés = _snapshots(db)
        stats = db.scalar(select(func.count()).select_from(TeamMatchStats)) or 0

        second = _run(db, client)
        db.commit()

        assert second.status == "applied"
        assert second.totals["links_created"] == 0
        assert second.totals["links_reused"] == 2
        assert second.totals["xg_written"] == 0
        assert second.totals["stats_created"] == 0
        assert second.totals["markets_written"] == 0
        assert second.totals["snapshots_written"] == 0
        assert db.scalar(select(func.count()).select_from(Market)) == marches
        assert _snapshots(db) == relevés
        assert db.scalar(select(func.count()).select_from(TeamMatchStats)) == stats
        assert db.scalar(select(func.count()).select_from(CsvLink)) == 3


def test_existing_xg_is_never_overwritten(world, engine, storage) -> None:
    client = FakeCsvClient({"F1": _f1_csv()})
    with Session(engine) as db:
        existant = TeamMatchStats(
            match_id=world["matches"]["rennes"],
            team_id=world["teams"]["rennes"],
            is_home=True,
            goals_for=1,
            goals_against=2,
            expected_goals=0.42,
            extra={"xg_source": "saisie"},
            data_source="bigballsdata",
        )
        db.add(existant)
        db.commit()

        report = _run(db, client)
        db.commit()

        db.refresh(existant)
        assert existant.expected_goals == pytest.approx(0.42)
        assert existant.extra == {"xg_source": "saisie"}
        assert existant.data_source == "bigballsdata"
        # L'autre équipe n'avait pas de xG : il est créé, avec sa provenance.
        cree = _stats(db, world["matches"]["rennes"], world["teams"]["lille"])
        assert cree is not None
        assert cree.expected_goals == pytest.approx(0.36)
        assert cree.extra == {"xg_source": "csv"}
        assert report.totals["xg_kept"] == 1
        assert report.totals["stats_created"] >= 1


def test_manual_market_is_kept(world, engine, storage) -> None:
    """Un marché saisi à la main n'est ni complété ni écrasé."""
    client = FakeCsvClient({"F1": _f1_csv()})
    with Session(engine) as db:
        template = resolve_template(db, "football.resultat_1x2")
        assert template is not None
        signature = build_signature(
            template_code=template.code,
            name=template.name,
            family=template.family,
            period=template.period,
            subject=template.subject,
            subject_team_id=None,
            subject_player=None,
            line=None,
            line2=None,
        )
        manuel = Market(
            match_id=world["matches"]["rennes"],
            template_code=template.code,
            name=template.name,
            family=template.family,
            period=template.period,
            subject=template.subject,
            signature=signature,
            is_custom=True,
            notes="saisie manuelle",
            selections=[
                Selection(code="1", label="Domicile", sort_order=0),
                Selection(code="X", label="Nul", sort_order=1),
                Selection(code="2", label="Extérieur", sort_order=2),
            ],
        )
        db.add(manuel)
        db.commit()

        report = _run(db, client)
        db.commit()

        assert report.leagues[0].manual_kept == 1
        db.refresh(manuel)
        assert manuel.is_custom is True
        assert manuel.notes == "saisie manuelle"
        assert all(not selection.snapshots for selection in manuel.selections)
        # Le marché manuel n'a pas été recréé : un seul 1X2 pour cette rencontre.
        resultats = [
            market
            for market in db.scalars(
                select(Market).where(Market.match_id == world["matches"]["rennes"])
            ).all()
            if market.template_code == "football.resultat_1x2"
        ]
        assert len(resultats) == 1


def test_pending_line_writes_nothing(world, engine, storage) -> None:
    """Sans rencontre correspondante, la ligne est enregistrée et n'écrit rien."""
    client = FakeCsvClient({"F1": _f1_csv()})
    with Session(engine) as db:
        report = _run(db, client)
        db.commit()

        assert report.leagues[0].unmatched == 1
        assert report.totals["snapshots_written"] >= 0
        pending = db.scalars(
            select(CsvLink).where(CsvLink.status == "pending")
        ).all()
        assert len(pending) == 1
        assert pending[0].match_id is None
        assert pending[0].row_key == "F1|2026-11-07|2-0|1-0|troyes|le mans"
        assert pending[0].confidence is None  # aucun candidat : aucun score inventé
        # Seules les deux rencontres connues reçoivent du xG (deux lignes chacune).
        assert db.scalar(select(func.count()).select_from(TeamMatchStats)) == 4
        assert db.scalar(select(func.count()).select_from(Market)) == 4


def test_network_failure_reuses_the_last_local_file(world, engine, storage) -> None:
    client = FakeCsvClient({"F1": _f1_csv()})
    with Session(engine) as db:
        _download(db, client)
        db.commit()

        report = _run(db, FakeCsvClient({"F1": _f1_csv()}, failing={"F1"}))
        db.commit()

        assert report.status == "partial"
        fichier = report.files[0]
        assert fichier.status == "partial"
        assert fichier.reused is True
        assert fichier.warnings and "réutilisé" in fichier.warnings[0]
        # La passe reste exploitable : les deux rencontres sont enrichies.
        assert report.leagues[0].matched == 2


def test_refresh_false_never_calls_the_network(world, engine, storage) -> None:
    client = FakeCsvClient({"F1": _f1_csv()})
    with Session(engine) as db:
        _download(db, client)
        db.commit()

        report = _run(db, OfflineClient(), refresh=False)
        db.commit()

        assert report.status == "applied"
        assert report.files[0].reused is True
        assert report.leagues[0].matched == 2


def test_download_stores_file_and_sidecar(world, engine, storage) -> None:
    client = FakeCsvClient({"F1": _f1_csv()})
    with Session(engine) as db:
        report = _download(db, client)
        db.commit()

        assert report.status == "applied"
        assert report.totals == {"files": 1, "rows": 3}
        fichier = storage / "F1.csv"
        assert fichier.read_bytes() == _f1_csv()
        sidecar = (storage / "F1.json").read_text(encoding="utf-8")
        assert '"rows": 3' in sidecar
        assert '"sha256"' in sidecar
        # Un téléchargement n'écrit jamais dans les rencontres.
        assert db.scalar(select(func.count()).select_from(CsvLink)) == 0
        assert _snapshots(db) == 0


def test_overview_reports_coverage_and_pending(world, engine, storage) -> None:
    client = FakeCsvClient({"F1": _f1_csv()})
    with Session(engine) as db:
        _run(db, client)
        db.commit()

        vue = csv_sync.overview(db)

        assert vue["provider"] == "football_data_uk"
        assert vue["configured"] is True
        assert len(vue["files"]) == 5
        stockes = [item for item in vue["files"] if item["stored"]]
        assert len(stockes) == 1
        assert stockes[0]["code"] == "ligue1"
        assert stockes[0]["rows"] == 3
        assert vue["totals"]["links_applied"] == 2
        assert vue["totals"]["links_pending"] == 1
        assert vue["totals"]["xg_rows"] == 4
        assert vue["totals"]["closing_markets"] == 4

        ligue1 = next(item for item in vue["coverage"] if item["code"] == "ligue1")
        assert ligue1["finished"] == 3  # la rencontre manuelle compte aussi
        assert ligue1["covered"] == 2
        assert ligue1["links_applied"] == 2

        assert len(vue["pending"]) == 1
        assert vue["pending"][0]["label"] == "Troyes — Le Mans"
        assert vue["last_run"] is not None
        assert vue["last_run"].operation == "csv"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_csv_routes_require_authentication(guest) -> None:
    assert guest.get("/api/v1/sync/csv/overview").status_code == 401
    assert guest.post("/api/v1/sync/csv/download", json={}).status_code == 401
    assert guest.post("/api/v1/sync/csv/run", json={}).status_code == 401


def test_csv_routes_require_csrf(auth_client) -> None:
    del auth_client.headers["X-CSRF-Token"]
    assert auth_client.post("/api/v1/sync/csv/run", json={}).status_code == 403


def test_csv_overview_route_shape(auth_client, storage) -> None:
    response = auth_client.get("/api/v1/sync/csv/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "football_data_uk"
    assert payload["configured"] is True
    assert len(payload["files"]) == 5
    assert payload["totals"]["files"] == 0
    assert payload["totals"]["rows"] == 0
    assert payload["pending"] == []
    assert payload["last_run"] is None


def test_csv_run_route_serialises_the_report(auth_client, storage, monkeypatch) -> None:
    rapport = csv_sync.CsvReport(
        status="applied",
        directory=str(storage),
        files=[
            csv_sync.CsvFileReport(
                code="ligue1",
                division="F1",
                name="Ligue 1 (F1)",
                season_label="2026-2027",
                rows=3,
                sha256="a" * 64,
            )
        ],
        leagues=[
            csv_sync.CsvLeagueReport(
                code="ligue1",
                division="F1",
                name="Ligue 1 (F1)",
                rows=3,
                matched=2,
                unmatched=1,
                xg_written=2,
                markets_written=4,
                snapshots_written=10,
            )
        ],
    )
    monkeypatch.setattr(csv_sync, "run", lambda db, **kwargs: rapport)

    response = auth_client.post("/api/v1/sync/csv/run", json={"leagues": ["ligue1"]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "football_data_uk"
    assert payload["status"] == "applied"
    assert payload["files"][0]["rows"] == 3
    assert payload["leagues"][0]["xg_written"] == 2
    assert payload["totals"]["snapshots_written"] == 10
