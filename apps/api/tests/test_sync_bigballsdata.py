"""Tests de la synchronisation BigBallsData (phase 15, étape 2).

Les charges viennent de réponses réelles enregistrées dans
``tests/fixtures/bbd/`` : une rencontre terminée, une rencontre à venir, les
statistiques de la rencontre terminée, le classement de Ligue 1 et le
catalogue des compétitions.

Le service reçoit un client simulé : aucun appel réseau n'est effectué.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.connectors.base import BudgetExceededError
from app.connectors.bigballsdata.importer import upsert_team
from app.connectors.quota import get_usage
from app.core.config import settings
from app.models.connector import SyncRun
from app.models.match import Match, MatchStatus, TeamMatchStats
from app.models.reference import Competition, Season, Sport, Team
from app.models.snapshot import StandingsSnapshot
from app.services import synchronization as service
from sqlalchemy import func, select
from sqlalchemy.orm import Session

FIXTURES = Path(__file__).parent / "fixtures" / "bbd"
MOMENT = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)

MATCH_ID = "ed2ec8f9-71d2-4b58-bc2f-95c61f922336"
HOME_ID = "466359e7-b471-4166-ae1b-9808edc8cf5d"
AWAY_ID = "2a8fb58a-598f-403b-9f83-8f67cb15d0b1"


def load(name: str) -> Any:
    """Charge une réponse réelle enregistrée."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def payload(name: str) -> Any:
    return load(name)["data"]


class FakeClient:
    """Client BigBallsData simulé, alimenté par les fixtures."""

    provider = "bigballsdata"

    def __init__(self, *, stats: bool = True) -> None:
        self.matches = {
            "finished": payload("matches-finished.json"),
            "scheduled": payload("matches-scheduled.json"),
        }
        self.statistics = payload("match-statistics.json") if stats else {}
        self.standings = payload("standings.json")["standings"][0]["rows"]
        self.leagues = payload("leagues.json")
        self.calls: list[str] = []
        self.seasons: set[str] = set()

    def list_leagues(self) -> list[dict[str, Any]]:
        self.calls.append("leagues")
        return self.leagues

    def list_matches(
        self,
        *,
        league: str,
        season: str,
        limit: int,
        offset: int,
        status: str,
    ) -> list[dict[str, Any]]:
        self.calls.append(f"matches:{league}:{status}:{offset}")
        self.seasons.add(season)
        rows = self.matches.get(status, [])
        return rows[offset : offset + limit]

    def get_statistics(self, match_id: str) -> dict[str, Any]:
        self.calls.append(f"stats:{match_id}")
        return self.statistics

    def get_standings(self, *, league: str, season: str) -> list[dict[str, Any]]:
        self.calls.append(f"standings:{league}")
        self.seasons.add(season)
        return self.standings

    def close(self) -> None:  # pragma: no cover - jamais appelé en test
        raise AssertionError("Le client simulé ne doit pas être fermé.")


@pytest.fixture()
def period(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fige la saison demandée au fournisseur."""
    monkeypatch.setattr(settings, "bigballsdata_season", "2026")


def run(db: Session, client: FakeClient, **options: Any) -> Any:
    return service.run_sync(
        db,
        leagues=["ligue1"],
        now=MOMENT,
        client=client,
        sleep=lambda _seconds: None,
        **options,
    )


def test_sync_writes_matches_teams_and_season(engine, seeded: None, period: None) -> None:
    client = FakeClient()
    with Session(engine) as db:
        report = run(db, client)
        db.commit()

        assert report.status == "applied"
        assert report.season == "2026"
        assert client.seasons == {"2026"}

        competition = db.scalar(select(Competition).where(Competition.code == "ligue1"))
        assert competition is not None
        assert competition.name == "Ligue 1"
        assert competition.country == "france"
        assert competition.is_active is True

        season = db.scalar(select(Season).where(Season.competition_id == competition.id))
        assert season is not None
        assert season.label == "2026-2027"
        assert season.external_label == "2026"
        assert season.is_current is True

        home = db.scalar(select(Team).where(Team.external_id == HOME_ID))
        away = db.scalar(select(Team).where(Team.external_id == AWAY_ID))
        assert home is not None and home.name == "Lens" and home.short_name == "RCL"
        assert home.logo_url is not None
        assert away is not None and away.name == "Marseille"

        finished = db.scalar(select(Match).where(Match.external_id == MATCH_ID))
        assert finished is not None
        assert finished.status == MatchStatus.TERMINE
        assert (finished.home_score, finished.away_score) == (1, 2)
        # `linescore` donne les buts par mi-temps : le premier élément est la pause.
        assert (finished.half_time_home_score, finished.half_time_away_score) == (1, 1)
        assert finished.round_name == "Regular Season - 10"
        assert finished.broadcast == "beIn Sports"
        assert finished.attendance is None
        assert finished.has_odds is True
        assert finished.data_source == "bigballsdata"
        assert finished.source_updated_at is not None

        scheduled = db.scalars(
            select(Match).where(Match.external_id != MATCH_ID)
        ).all()
        assert len(scheduled) == 1
        assert scheduled[0].status == MatchStatus.PROGRAMME
        assert scheduled[0].home_score is None

        assert report.totals["created"] == 2
        assert report.totals["teams_created"] == 4
        assert report.totals["stats_requested"] == 0


def test_sync_writes_statistics_without_expected_goals(
    engine, seeded: None, period: None
) -> None:
    client = FakeClient()
    with Session(engine) as db:
        run(db, client, include_stats=True, stats_limit=10)
        db.commit()

        rows = db.scalars(select(TeamMatchStats)).all()
        assert len(rows) == 2
        by_home = {row.is_home: row for row in rows}
        home = by_home[True]
        away = by_home[False]
        assert home.shots == 13 and home.shots_on_target == 6
        assert home.possession == 41.0 and home.corners == 4
        assert home.goals_for == 1 and home.goals_against == 2
        assert home.pass_percentage is None
        assert away.shots == 16 and away.goals_for == 2
        assert away.goalkeeper_saves == 5
        # BigBallsData ne fournit pas le xG : la colonne reste vide.
        assert home.expected_goals is None
        assert away.expected_goals is None
        assert home.data_source == "bigballsdata"


def test_statistics_absent_at_source_are_reported_not_invented(
    engine, seeded: None, period: None
) -> None:
    class SansStatistiques(FakeClient):
        def get_statistics(self, match_id: str) -> dict[str, Any]:
            self.calls.append(f"stats:{match_id}")
            return {"home": None, "away": None}

    with Session(engine) as db:
        report = run(db, SansStatistiques(), include_stats=True, stats_limit=10)
        db.commit()

        assert db.scalar(select(func.count()).select_from(TeamMatchStats)) == 0
        item = report.leagues[0]
        assert item.stats_requested == 1
        assert item.stats_missing == 1
        assert any("sans statistiques" in avertissement for avertissement in item.warnings)


def _fiche(
    base: dict[str, Any],
    *,
    external_id: str,
    round_name: str | None,
    score: dict[str, int] | None,
) -> dict[str, Any]:
    """Copie une charge réelle en changeant l'identité, la journée et le score."""
    copie = json.loads(json.dumps(base))
    copie["id"] = external_id
    copie["round"] = round_name
    copie["score"] = score
    return copie


def test_second_sheet_for_the_same_fixture_is_ignored(
    engine, seeded: None, period: None
) -> None:
    complete = payload("matches-finished.json")[0]
    degradee = _fiche(
        complete,
        external_id="fiche-degradee",
        round_name=None,
        score={"home": 0, "away": 0},
    )

    class DeuxFiches(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.matches["finished"] = [complete, degradee]
            self.matches["scheduled"] = []

    with Session(engine) as db:
        report = run(db, DeuxFiches())
        db.commit()

        assert db.scalar(select(func.count()).select_from(Match)) == 1
        gardee = db.scalar(select(Match))
        assert gardee is not None
        assert gardee.external_id == MATCH_ID
        assert gardee.round_name == "Regular Season - 10"
        assert (gardee.home_score, gardee.away_score) == (1, 2)
        assert report.leagues[0].duplicates == 1
        assert any("en double" in avertissement for avertissement in report.leagues[0].warnings)


def test_degraded_sheet_is_replaced_in_place(
    engine, seeded: None, period: None
) -> None:
    complete = payload("matches-finished.json")[0]
    degradee = _fiche(
        complete,
        external_id="fiche-degradee",
        round_name=None,
        score={"home": 0, "away": 0},
    )

    class DegradeeSeule(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.matches["finished"] = [degradee]
            self.matches["scheduled"] = []

    class LesDeux(DegradeeSeule):
        def __init__(self) -> None:
            super().__init__()
            self.matches["finished"] = [degradee, complete]

    with Session(engine) as db:
        run(db, DegradeeSeule())
        db.commit()
        ligne = db.scalar(select(Match))
        assert ligne is not None
        identifiant = ligne.id
        assert ligne.external_id == "fiche-degradee"

        run(db, LesDeux())
        db.commit()
        assert db.scalar(select(func.count()).select_from(Match)) == 1
        ligne = db.get(Match, identifiant)
        assert ligne is not None
        assert ligne.external_id == MATCH_ID
        assert ligne.round_name == "Regular Season - 10"
        assert (ligne.home_score, ligne.away_score) == (1, 2)


def test_existing_expected_goals_are_never_overwritten(
    engine, seeded: None, period: None
) -> None:
    client = FakeClient()
    with Session(engine) as db:
        run(db, client)
        db.commit()

        match = db.scalar(select(Match).where(Match.external_id == MATCH_ID))
        home = db.scalar(select(Team).where(Team.external_id == HOME_ID))
        assert match is not None and home is not None
        db.add(
            TeamMatchStats(
                match_id=match.id,
                team_id=home.id,
                is_home=True,
                shots=1,
                expected_goals=1.5,
                data_source="football_data_uk",
            )
        )
        db.commit()

        run(db, client, include_stats=True, stats_limit=10)
        db.commit()
        row = db.scalar(
            select(TeamMatchStats).where(
                TeamMatchStats.match_id == match.id,
                TeamMatchStats.team_id == home.id,
            )
        )
        assert row is not None
        assert row.expected_goals == 1.5
        assert row.shots == 13
        assert row.data_source == "bigballsdata"


def test_sync_writes_standings_but_ignores_unknown_teams(
    engine, seeded: None, period: None
) -> None:
    client = FakeClient()
    with Session(engine) as db:
        run(db, client, include_standings=True)
        db.commit()

        rows = db.scalars(select(StandingsSnapshot)).all()
        # Les quatre équipes des deux rencontres existent en base ; les autres
        # lignes du classement sont ignorées, jamais inventées.
        assert len(rows) == 4
        by_team = {row.team_id: row for row in rows}
        home = db.scalar(select(Team).where(Team.external_id == HOME_ID))
        assert home is not None
        lens = by_team[home.id]
        assert lens.rank == 11
        assert lens.played == 10
        assert lens.wins == 4
        assert lens.draws == 1
        assert lens.losses == 5
        # `points_for` et `points_against` sont des buts, pas des points.
        assert lens.goals_for == 17
        assert lens.goals_against == 15
        assert lens.points is None


def test_second_pass_is_idempotent(engine, seeded: None, period: None) -> None:
    client = FakeClient()
    with Session(engine) as db:
        first = run(db, client, include_stats=True, include_standings=True, stats_limit=10)
        db.commit()
        second = run(db, client, include_stats=True, include_standings=True, stats_limit=10)
        db.commit()

        assert first.totals["created"] == 2
        assert second.totals["created"] == 0
        assert second.totals["updated"] == 0
        assert second.totals["unchanged"] == 2
        assert second.totals["stats_written"] == 0
        assert second.totals["standings_written"] == 0
        assert db.scalar(select(func.count()).select_from(Match)) == 2
        assert db.scalar(select(func.count()).select_from(TeamMatchStats)) == 2
        assert db.scalar(select(func.count()).select_from(StandingsSnapshot)) == 4


def test_manual_match_is_never_touched(engine, seeded: None, period: None) -> None:
    with Session(engine) as db:
        sport = db.scalar(select(Sport).where(Sport.code == "football"))
        assert sport is not None
        competition = Competition(
            sport_id=sport.id,
            name="Ligue 1",
            country="France",
        )
        db.add(competition)
        db.flush()
        season = Season(
            competition_id=competition.id,
            label="2026-2027",
            is_current=True,
        )
        db.add(season)
        db.flush()
        manual_home = Team(sport_id=sport.id, name="Équipe Manuelle")
        manual_away = Team(sport_id=sport.id, name="Autre Équipe")
        db.add_all([manual_home, manual_away])
        db.flush()
        manual = Match(
            season_id=season.id,
            home_team_id=manual_home.id,
            away_team_id=manual_away.id,
            kickoff_at=MOMENT,
            status=MatchStatus.PROGRAMME,
            home_score=3,
            away_score=3,
            data_source="manual",
        )
        db.add(manual)
        db.commit()
        manual_id = manual.id
        competition_id = competition.id
        season_id = season.id

        report = run(db, FakeClient())
        db.commit()

        assert report.status == "applied"
        manual = db.get(Match, manual_id)
        assert manual is not None
        assert manual.external_id is None
        assert manual.data_source == "manual"
        assert (manual.home_score, manual.away_score) == (3, 3)
        # La compétition et la saison manuelles sont reprises, pas dupliquées.
        competition = db.get(Competition, competition_id)
        assert competition is not None and competition.code == "ligue1"
        assert db.get(Season, season_id) is not None
        assert db.scalar(select(func.count()).select_from(Competition)) == 1
        assert db.scalar(select(func.count()).select_from(Season)) == 1
        assert db.scalar(select(func.count()).select_from(Match)) == 3


def test_manual_team_is_adopted_instead_of_duplicated(
    engine, seeded: None, period: None
) -> None:
    with Session(engine) as db:
        sport = db.scalar(select(Sport).where(Sport.code == "football"))
        assert sport is not None
        manual = Team(sport_id=sport.id, name="Lens")
        db.add(manual)
        db.commit()
        manual_id = manual.id

        run(db, FakeClient())
        db.commit()

        adopted = db.get(Team, manual_id)
        assert adopted is not None
        assert adopted.external_id == HOME_ID
        # Lens reprise + Marseille + Troyes + Le Havre : aucune copie de Lens.
        assert db.scalar(select(func.count()).select_from(Team)) == 4


def test_budget_exhausted_mid_pass_returns_partial(
    engine, seeded: None, period: None
) -> None:
    with Session(engine) as db:
        usage = get_usage(db, "bigballsdata")
        usage.limit = 3
        db.commit()

        report = service.run_sync(
            db,
            leagues=["ligue1", "laliga"],
            now=MOMENT,
            client=FakeClient(),
            sleep=lambda _seconds: None,
        )
        db.commit()

        assert report.status == "partial"
        assert [item.status for item in report.leagues] == ["applied", "failed"]
        assert "Budget insuffisant" in (report.leagues[1].error or "")
        assert db.scalar(select(func.count()).select_from(Match)) == 2
        # Le journal garde une ligne par compétition tentée.
        runs = db.scalars(select(SyncRun).order_by(SyncRun.created_at)).all()
        assert [run.params["league"] for run in runs] == ["ligue1", "laliga"]
        assert runs[0].status == "applied"
        assert runs[1].status == "failed"


def test_pass_is_logged_without_any_secret(
    engine, seeded: None, period: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "cle-secrete-jamais-journalisee"
    monkeypatch.setattr(settings, "bigballsdata_key", secret)
    with Session(engine) as db:
        report = run(db, FakeClient())
        db.commit()

        runs = db.scalars(select(SyncRun)).all()
        assert len(runs) == 1
        run_row = runs[0]
        assert run_row.provider == "bigballsdata"
        assert run_row.operation == "fixtures"
        assert run_row.params["league"] == "ligue1"
        assert run_row.summary["counts"]["received"] == 2
        # Le journal d'une compétition compte ses propres appels ; la requête
        # de catalogue est commune et comptée dans le total de la passe.
        assert run_row.requests_used == 2
        assert report.requests == 3

        payloads = json.dumps(
            {
                "report": report.as_dict(),
                "overview": service.overview(db),
            },
            default=str,
        )
        assert secret not in payloads


def test_overview_lists_tracked_leagues(engine, seeded: None, period: None) -> None:
    with Session(engine) as db:
        overview = service.overview(db)
        assert overview["provider"] == "bigballsdata"
        assert len(overview["leagues"]) == 7
        codes = [item["code"] for item in overview["leagues"]]
        assert codes == list(service.TRACKED_LEAGUES)
        assert overview["quota"]["limit"] == settings.bigballsdata_daily_budget
        assert overview["totals"]["matches"] == 0

        run(db, FakeClient(), include_stats=True, stats_limit=10)
        db.commit()
        overview = service.overview(db)
        ligue1 = next(item for item in overview["leagues"] if item["code"] == "ligue1")
        assert ligue1["name"] == "Ligue 1"
        assert ligue1["season_label"] == "2026-2027"
        assert ligue1["finished"] == 1
        assert ligue1["upcoming"] == 1
        assert ligue1["last_status"] == "applied"
        assert overview["totals"]["matches"] == 2
        assert overview["totals"]["stats_rows"] == 2
        assert overview["totals"]["xg_rows"] == 0


def test_bigballsdata_quota_errors_surface_as_failed(
    engine, seeded: None, period: None
) -> None:
    class Failing(FakeClient):
        def list_leagues(self) -> list[dict[str, Any]]:
            raise BudgetExceededError("Budget refusé avant l'appel.")

    with Session(engine) as db:
        report = run(db, Failing())
        assert report.status == "failed"
        assert report.error is not None and "Budget refusé" in report.error
        assert db.scalar(select(func.count()).select_from(SyncRun)) == 0


def test_sync_routes(auth_client, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.synchronization import SyncReport

    response = auth_client.get("/api/v1/sync/overview")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["provider"] == "bigballsdata"
    assert len(data["leagues"]) == 7
    assert data["runs"] == []

    assert auth_client.get("/api/v1/sync/runs").json() == []

    def fake_run(db, **_options):
        return SyncReport(status="applied", season="2026")

    monkeypatch.setattr("app.api.v1.sync.service.run_sync", fake_run)
    response = auth_client.post(
        "/api/v1/sync/run",
        json={"leagues": ["ligue1"], "include_stats": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "applied"
    assert response.json()["totals"]["matches"] == 0


def test_sync_routes_require_authentication(guest) -> None:
    assert guest.get("/api/v1/sync/overview").status_code == 401
    assert guest.post("/api/v1/sync/run", json={}).status_code == 401


def test_upsert_team_refuses_two_provider_ids_for_one_name(
    engine, seeded: None
) -> None:
    from app.connectors.base import NormalizedTeam
    from app.connectors.bigballsdata.importer import ImportConflict

    with Session(engine) as db:
        sport = db.scalar(select(Sport).where(Sport.code == "football"))
        assert sport is not None
        db.add(Team(sport_id=sport.id, name="Lens", external_id="ancien-id"))
        db.commit()

        with pytest.raises(ImportConflict):
            upsert_team(
                db,
                sport_id=sport.id,
                team=NormalizedTeam(external_id=HOME_ID, name="Lens"),
            )
