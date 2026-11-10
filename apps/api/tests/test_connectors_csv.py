"""Tests du connecteur football-data.co.uk : aucun appel réseau."""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from app.connectors.base import PreviewCounts, ProviderNotCoveredError
from app.connectors.football_data_uk.mapping import (
    CsvRow,
    CsvTeamStats,
    build_url,
    parse_rows,
    season_code,
)
from app.models.connector import ConnectorLink, ProviderRef, SyncRun
from app.models.match import Match, MatchStatus, TeamMatchStats
from app.models.reference import Competition, Season, Sport, Team
from app.services import connectors as service
from sqlalchemy import func, select
from sqlalchemy.orm import Session

COMPETITION = "Ligue 1 CSV"
SAISON = "2026-2027"

_ENTETE = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,"
    "HxG,AxG,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR"
)
CSV = (
    _ENTETE
    + "\n"
    + "F1,21/08/2026,20:45,Marseille,Strasbourg,4,0,H,0,0,D,2.35,0.72,18,7,8,2,12,15,6,3,1,2,0,0\n"
    + "F1,22/08/2026,20:45,Troyes,Paris FC,1,2,A,1,1,D,0.95,1.62,9,14,3,6,14,11,4,5,3,1,0,0\n"
    + "F1,23/08/2026,17:00,Paris SG,Lens,3,1,H,1,0,H,2.90,1.05,21,8,10,3,9,13,7,2,0,3,0,0\n"
    + "F1,30/08/2026,20:45,Angers,Lyon,,,,,,,,,,,,,,,,,,,\n"
)

EQUIPES = (
    "Olympique de Marseille",
    "RC Strasbourg Alsace",
    "ES Troyes AC",
    "Paris FC",
    "Paris Saint-Germain FC",
    "RC Lens",
    "Angers SCO",
    "Olympique Lyonnais",
)


def _require[T](value: T | None) -> T:
    assert value is not None
    return value


@pytest.fixture()
def seeded_db(seeded: None, engine) -> None:
    return None


def _setup(engine) -> str:
    """Crée la compétition, la saison, les équipes et le calendrier interne."""
    with Session(engine) as db:
        sport = _require(db.scalar(select(Sport).where(Sport.code == "football")))
        competition = Competition(sport_id=sport.id, name=COMPETITION)
        db.add(competition)
        db.flush()
        season = Season(competition_id=competition.id, label=SAISON, is_current=True)
        db.add(season)
        db.flush()
        equipes = {nom: Team(sport_id=sport.id, name=nom) for nom in EQUIPES}
        db.add_all(equipes.values())
        db.flush()
        rencontres = (
            ("Olympique de Marseille", "RC Strasbourg Alsace", datetime(2026, 8, 21, 20, 45)),
            ("ES Troyes AC", "Paris FC", datetime(2026, 8, 22, 19, 45)),
            ("Paris Saint-Germain FC", "RC Lens", datetime(2026, 8, 23, 16, 0)),
        )
        for domicile, exterieur, coup in rencontres:
            db.add(
                Match(
                    season_id=season.id,
                    home_team_id=equipes[domicile].id,
                    away_team_id=equipes[exterieur].id,
                    kickoff_at=coup.replace(tzinfo=UTC),
                    status=MatchStatus.PROGRAMME,
                    data_source="football_data",
                )
            )
        link = ConnectorLink(
            provider="football_data_uk",
            competition_id=competition.id,
            season_id=season.id,
            external_league_id="F1",
            external_season="2026",
        )
        db.add(link)
        db.commit()
        return str(link.id)


def _link(db: Session) -> ConnectorLink:
    return _require(db.scalar(select(ConnectorLink)))


# ---------------------------------------------------------------------------
# Lecture du fichier
# ---------------------------------------------------------------------------


def test_season_code_and_url() -> None:
    assert season_code("2026") == "2627"
    assert season_code("2026-2027") == "2627"
    assert build_url("https://football-data.co.uk", "F1", "2026") == (
        "https://football-data.co.uk/mmz4281/2627/F1.csv"
    )
    assert (
        build_url(
            "https://football-data.co.uk",
            "https://www.football-data.co.uk/mmz4281/2627/F1.csv",
            "2026",
        )
        == "https://www.football-data.co.uk/mmz4281/2627/F1.csv"
    )
    with pytest.raises(ProviderNotCoveredError):
        season_code("inconnue")
    with pytest.raises(ProviderNotCoveredError):
        build_url("https://football-data.co.uk", "../secret", "2026")
    with pytest.raises(ProviderNotCoveredError):
        build_url(
            "https://football-data.co.uk",
            "https://football-data.co.uk.attaquant.example/mmz4281/2627/F1.csv",
            "2026",
        )
    with pytest.raises(ProviderNotCoveredError):
        build_url(
            "https://football-data.co.uk",
            "http://football-data.co.uk/mmz4281/2627/F1.csv",
            "2026",
        )


def test_parse_rows_reads_xg_and_skips_unplayed() -> None:
    lignes = parse_rows(CSV, division="F1")
    assert len(lignes) == 3
    premiere = lignes[0]
    assert premiere.home_name == "Marseille"
    assert premiere.played_on.isoformat() == "2026-08-21"
    assert (premiere.home_score, premiere.away_score) == (4, 0)
    assert (premiere.half_time_home, premiere.half_time_away) == (0, 0)
    assert premiere.home_stats.expected_goals == pytest.approx(2.35)
    assert premiere.away_stats.expected_goals == pytest.approx(0.72)
    assert premiere.home_stats.shots_on_target == 8
    assert premiere.away_stats.corners == 3
    assert premiere.home_stats.as_dict()["extra"] == {"fouls": 12}


# ---------------------------------------------------------------------------
# Aperçu et application
# ---------------------------------------------------------------------------


def test_preview_then_apply(engine, seeded_db) -> None:
    _setup(engine)
    with Session(engine) as db:
        link = _link(db)
        rows = parse_rows(CSV, division="F1")
        plan, counts, skipped = _projection(db, link, rows)
        assert counts.received == 3
        assert counts.updated == 3
        assert counts.created == 3
        assert counts.conflicts == 0
        assert skipped == []
        assert db.scalar(select(func.count()).select_from(TeamMatchStats)) == 0

        resultat = service.apply_preview(db, _run(db, link, plan))
        db.commit()
        assert resultat.updated == 3
        assert resultat.created == 3
        assert db.scalar(select(func.count()).select_from(TeamMatchStats)) == 6

        marseille = _require(
            db.scalar(select(Match).where(Match.home_score == 4, Match.away_score == 0))
        )
        assert marseille.status == MatchStatus.TERMINE
        assert marseille.data_source == "football_data_uk"
        stats = db.scalars(
            select(TeamMatchStats).where(
                TeamMatchStats.match_id == marseille.id, TeamMatchStats.is_home.is_(True)
            )
        ).all()
        assert len(stats) == 1
        assert stats[0].expected_goals == pytest.approx(2.35)
        assert stats[0].shots_on_target == 8
        assert stats[0].data_source == "football_data_uk"


def test_second_apply_creates_nothing(engine, seeded_db) -> None:
    _setup(engine)
    with Session(engine) as db:
        link = _link(db)
        rows = parse_rows(CSV, division="F1")
        plan, _, _ = _projection(db, link, rows)
        service.apply_preview(db, _run(db, link, plan))
        db.commit()

        plan2, counts2, _ = _projection(db, link, rows)
        assert counts2.created == 0
        assert counts2.updated == 0
        assert counts2.conflicts == 3
        service.apply_preview(db, _run(db, link, plan2))
        db.commit()
        assert db.scalar(select(func.count()).select_from(TeamMatchStats)) == 6


def test_manual_score_is_never_overwritten(engine, seeded_db) -> None:
    _setup(engine)
    with Session(engine) as db:
        match = _require(
            db.scalar(
                select(Match).where(
                    Match.home_team_id.is_not(None),
                    Match.status == MatchStatus.PROGRAMME,
                )
            )
        )
        match.data_source = "manual"
        match.home_score = 0
        match.away_score = 0
        db.commit()

        rows = parse_rows(CSV, division="F1")
        plan, counts, _ = _projection(db, _link(db), rows)
        assert counts.conflicts >= 1
        service.apply_preview(db, _run(db, _link(db), plan))
        db.commit()
        match = _require(db.get(Match, match.id))
        assert (match.home_score, match.away_score) == (0, 0)


def test_no_odds_are_imported(engine, seeded_db) -> None:
    from app.models.market import OddsSnapshot

    _setup(engine)
    with Session(engine) as db:
        rows = parse_rows(CSV, division="F1")
        plan, _, _ = _projection(db, _link(db), rows)
        service.apply_preview(db, _run(db, _link(db), plan))
        db.commit()
        assert db.scalar(select(func.count()).select_from(OddsSnapshot)) == 0


# ---------------------------------------------------------------------------
# Équipes et calendrier
# ---------------------------------------------------------------------------


def test_unknown_team_is_never_created(engine, seeded_db) -> None:
    _setup(engine)
    csv = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nF1,21/08/2026,Marseille,Inconnu FC,2,1\n"
    with Session(engine) as db:
        avant = db.scalar(select(func.count()).select_from(Team))
        plan, counts, skipped = _projection(db, _link(db), parse_rows(csv, division="F1"))
        db.commit()
        assert counts.conflicts == 1
        assert len(skipped) == 1
        assert skipped[0]["reason"] == "Équipe non reconnue"
        assert {equipe["csv_name"] for equipe in skipped[0]["teams"]} == {
            "Marseille",
            "Inconnu FC",
        }
        assert {equipe["external_id"] for equipe in skipped[0]["teams"]} == {
            "marseille",
            "inconnu",
        }
        assert db.scalar(select(func.count()).select_from(Team)) == avant
        assert plan["items"] == []


def test_team_link_resolves_unknown_name(engine, seeded_db) -> None:
    _setup(engine)
    csv = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nF1,21/08/2026,OM,Strasbourg,2,1\n"
    with Session(engine) as db:
        link = _link(db)
        equipe = _require(db.scalar(select(Team).where(Team.name == "Olympique de Marseille")))
        service.link_csv_team(db, link, "om", equipe.id)
        db.commit()
        _, counts, skipped = _projection(db, link, parse_rows(csv, division="F1"))
        db.commit()
        assert counts.updated == 1
        assert counts.created == 1
        assert skipped == []


def test_match_outside_calendar_is_ignored(engine, seeded_db) -> None:
    _setup(engine)
    csv = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nF1,15/11/2026,Lens,Marseille,1,1\n"
    with Session(engine) as db:
        _, counts, skipped = _projection(db, _link(db), parse_rows(csv, division="F1"))
        db.commit()
        assert counts.ignored == 1
        assert skipped[0]["reason"] == "Rencontre absente du calendrier interne"


# ---------------------------------------------------------------------------
# Aides locales : plan stocké puis exécuté comme un aperçu réel
# ---------------------------------------------------------------------------


def _projection(
    db: Session, link: ConnectorLink, rows: list[CsvRow]
) -> tuple[dict[str, Any], PreviewCounts, list[dict[str, Any]]]:
    """Exécute la planification du service sans passer par le réseau."""
    from app.connectors.football_data_uk.importer import plan_import

    competition = _require(db.get(Competition, link.competition_id))
    plan, counts, skipped = plan_import(
        db,
        provider="football_data_uk",
        season_id=link.season_id,
        sport_id=competition.sport_id,
        rows=rows,
    )
    plan["plan_kind"] = "results_stats"
    return plan, counts, skipped


def _run(db: Session, link: ConnectorLink, plan: dict) -> SyncRun:
    run = SyncRun(
        provider="football_data_uk",
        operation="results_stats",
        status="preview",
        link_id=link.id,
        payload=plan,
        summary={"counts": {}},
    )
    db.add(run)
    db.flush()
    return run


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


class _FauxClient:
    """Client CSV factice : aucune requête réseau."""

    def __init__(self, rows: list[CsvRow]) -> None:
        self._rows = rows

    def fetch_rows(self, **_: object) -> list[CsvRow]:
        return self._rows

    def close(self) -> None:
        return None


def _ligne(home: str = "Marseille", away: str = "Strasbourg") -> CsvRow:
    return CsvRow(
        division="F1",
        played_on=date(2026, 8, 21),
        kickoff="20:45",
        home_name=home,
        away_name=away,
        home_score=1,
        away_score=0,
        half_time_home=0,
        half_time_away=0,
        home_stats=CsvTeamStats(is_home=True, goals_for=1, goals_against=0),
        away_stats=CsvTeamStats(is_home=False, goals_for=0, goals_against=1),
    )


def _route_data(client, sport_id: str, season_id: str) -> dict[str, str]:
    """Crée deux équipes et la rencontre correspondante via l'API."""
    ids: dict[str, str] = {}
    for nom in ("Olympique de Marseille", "RC Strasbourg Alsace"):
        reponse = client.post("/api/v1/teams", json={"sport_id": sport_id, "name": nom})
        assert reponse.status_code == 201, reponse.text
        ids[nom] = reponse.json()["id"]
    reponse = client.post(
        "/api/v1/matches",
        json={
            "season_id": season_id,
            "home_team_id": ids["Olympique de Marseille"],
            "away_team_id": ids["RC Strasbourg Alsace"],
            "kickoff_at": "2026-08-21T20:45:00Z",
            "status": "programme",
        },
    )
    assert reponse.status_code == 201, reponse.text
    return ids


def _route_link(client, competition_id: str, season_id: str) -> dict:
    reponse = client.post(
        "/api/v1/connectors/links",
        json={
            "provider": "football_data_uk",
            "competition_id": competition_id,
            "season_id": season_id,
            "external_league_id": "F1",
            "external_season": "2026",
        },
    )
    assert reponse.status_code == 201, reponse.text
    return reponse.json()


def test_divisions_route(auth_client) -> None:
    reponse = auth_client.get("/api/v1/connectors/football-data-uk/divisions")
    assert reponse.status_code == 200, reponse.text
    codes = {item["external_id"] for item in reponse.json()}
    assert {"F1", "F2", "E0"} <= codes


def test_csv_preview_and_apply_route(
    auth_client, sport_id, competition_id, season_id, monkeypatch
) -> None:
    _route_data(auth_client, sport_id, season_id)
    link = _route_link(auth_client, competition_id, season_id)
    monkeypatch.setattr(service, "client_for", lambda *_, **__: _FauxClient([_ligne()]))

    reponse = auth_client.post(f"/api/v1/connectors/links/{link['id']}/csv/preview")
    assert reponse.status_code == 200, reponse.text
    data = reponse.json()
    assert data["provider"] == "football_data_uk"
    assert data["operation"] == "results_stats"
    assert data["status"] == "preview"
    assert data["counts"]["created"] == 1
    assert data["counts"]["updated"] == 1
    assert data["skipped"] == []
    assert data["quota"]["limit"] is None

    applied = auth_client.post(f"/api/v1/connectors/sync-runs/{data['run_id']}/apply")
    assert applied.status_code == 200, applied.text
    assert applied.json()["counts"]["created"] == 1
    assert applied.json()["counts"]["updated"] == 1

    replay = auth_client.post(f"/api/v1/connectors/sync-runs/{data['run_id']}/apply")
    assert replay.status_code == 409


def test_csv_team_link_route(
    auth_client, sport_id, competition_id, season_id, monkeypatch
) -> None:
    equipes = _route_data(auth_client, sport_id, season_id)
    link = _route_link(auth_client, competition_id, season_id)
    monkeypatch.setattr(
        service, "client_for", lambda *_, **__: _FauxClient([_ligne(home="OM")])
    )

    premier = auth_client.post(f"/api/v1/connectors/links/{link['id']}/csv/preview")
    assert premier.status_code == 200, premier.text
    assert premier.json()["counts"]["conflicts"] == 1
    equipe = premier.json()["skipped"][0]["teams"][0]
    assert equipe["csv_name"] == "OM"
    assert equipe["external_id"] == "om"
    assert equipe["status"] == "missing"

    associee = auth_client.post(
        f"/api/v1/connectors/football-data-uk/teams/link?link_id={link['id']}",
        json={"external_id": "om", "team_id": equipes["Olympique de Marseille"]},
    )
    assert associee.status_code == 204, associee.text

    second = auth_client.post(f"/api/v1/connectors/links/{link['id']}/csv/preview")
    assert second.status_code == 200, second.text
    assert second.json()["skipped"] == []
    assert second.json()["counts"]["created"] == 1
    assert second.json()["counts"]["updated"] == 1


def test_csv_preview_unknown_link_returns_404(auth_client) -> None:
    reponse = auth_client.post(
        "/api/v1/connectors/links/00000000-0000-0000-0000-000000000000/csv/preview"
    )
    assert reponse.status_code == 404


def test_provider_ref_is_stored_for_linked_team(
    auth_client, sport_id, competition_id, season_id, engine
) -> None:
    equipes = _route_data(auth_client, sport_id, season_id)
    link = _route_link(auth_client, competition_id, season_id)
    reponse = auth_client.post(
        f"/api/v1/connectors/football-data-uk/teams/link?link_id={link['id']}",
        json={"external_id": "om", "team_id": equipes["Olympique de Marseille"]},
    )
    assert reponse.status_code == 204, reponse.text
    with Session(engine) as db:
        ref = db.scalar(select(ProviderRef).where(ProviderRef.external_id == "om"))
        assert ref is not None
        assert ref.provider == "football_data_uk"
