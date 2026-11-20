"""Tests des snapshots équipes (phase 14A, étape 3).

Aucun appel réseau : le service reçoit un client simulé et la base est SQLite.
Les tests couvrent la normalisation, l'idempotence, le budget, les pannes et le
journal. Les valeurs reproduisent les formes réelles relevées le 18/11/2026.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from app.connectors.base import ConnectorError, ProviderAuthError, ProviderRateLimitError
from app.connectors.bigballsdata.client import BigBallsDataClient
from app.connectors.bigballsdata.snapshot_mapping import map_team_snapshot
from app.connectors.http import HttpClient
from app.connectors.quota import get_usage
from app.core.config import settings
from app.models.connector import SyncRun
from app.models.match import Match, MatchStatus
from app.models.reference import Competition, Season, Sport, Team
from app.models.snapshot import TeamSnapshot
from app.services.snapshots import run_snapshots
from sqlalchemy import func, select
from sqlalchemy.orm import Session

MOMENT = datetime(2026, 11, 18, 6, 30, tzinfo=UTC)
DAY = date(2026, 11, 18)

ELO = {
    "team_id": "t-1",
    "elo_rating": 1451,
    "games_counted": 44,
    "last_computed": "2026-11-10T06:03:18.248Z",
    "last_match_date": "2026-11-07",
}

STATS = {
    "matches_played": 118,
    "as_of": "2026-11-18T05:21:06.375Z",
    "wins": 29,
    "draws": 34,
    "losses": 55,
    "goals_scored": 130,
    "goals_conceded": 184,
    "clean_sheets": 27,
    "form_string": "LWDLL",
    "btts_rate": 0.551,
    "over_2_5_rate": 0.517,
}

SEASON = {
    "season": "2026-27",
    "as_of": "2026-11-18T05:02:57.227Z",
    "home_away_splits": {
        "home": {"wins": 2, "losses": 2, "ties": 1},
        "away": {"wins": 1, "losses": 4, "ties": 0},
    },
    "all_time_home_away_splits": {
        "home": {"wins": 20, "losses": 10, "ties": 5},
        "away": {"wins": 5, "losses": 20, "ties": 5},
    },
}

SECRET = "cle-secrete-snapshots-jamais-journalisee"


class FakeSnapshotClient:
    """Client BigBallsData simulé, sans réseau."""

    provider = "bigballsdata"

    def __init__(
        self,
        *,
        elo: Any = None,
        stats: Any = None,
        season: Any = None,
        usage: Any = None,
    ) -> None:
        self.elo = ELO if elo is None else elo
        self.stats = STATS if stats is None else stats
        self.season = SEASON if season is None else season
        self.usage = {"remaining": 1200} if usage is None else usage
        self.calls: list[str] = []

    def get_team_elo(self, team_id: str) -> Any:
        self.calls.append(f"elo:{team_id}")
        return self.elo

    def get_team_stats(self, team_id: str) -> Any:
        self.calls.append(f"stats:{team_id}")
        return self.stats

    def get_team_season(self, team_id: str) -> Any:
        self.calls.append(f"season:{team_id}")
        return self.season

    def get_usage(self) -> Any:
        self.calls.append("usage")
        return self.usage


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _team(db: Session, external_id: str, name: str) -> Team:
    sport = db.scalar(select(Sport).where(Sport.code == "football"))
    assert sport is not None
    row = Team(sport_id=sport.id, external_id=external_id, name=name)
    db.add(row)
    db.commit()
    return row


# --- Normalisation ---------------------------------------------------------


def test_mapping_combines_the_three_sources() -> None:
    row = map_team_snapshot(
        team_external_id="t-1",
        elo=ELO,
        stats=STATS,
        season=SEASON,
        captured_at=MOMENT,
        timezone="Europe/Paris",
    )

    assert row.captured_on == DAY
    assert _utc(row.captured_at) == MOMENT
    assert row.elo_rating == Decimal("1451")
    assert row.elo_games_counted == 44
    assert row.elo_last_match_date == date(2026, 11, 7)
    assert row.matches_played == 118
    assert row.btts_rate == Decimal("0.551")
    assert row.over_2_5_rate == Decimal("0.517")
    assert row.goals_scored == 130
    assert row.goals_conceded == 184
    assert row.clean_sheets == 27
    assert row.form_string == "LWDLL"
    # `ties` devient `draws`, et seuls les splits de la saison en cours sont lus.
    assert (row.home_wins, row.home_draws, row.home_losses) == (2, 1, 2)
    assert (row.away_wins, row.away_draws, row.away_losses) == (1, 0, 4)
    assert row.source_as_of == datetime(2026, 11, 10, 6, 3, 18, 248000, tzinfo=UTC)
    assert row.warnings == []


def test_source_as_of_is_the_oldest_timestamp() -> None:
    row = map_team_snapshot(
        team_external_id="t-1",
        elo={**ELO, "last_computed": "2026-11-18T05:00:00Z"},
        stats={**STATS, "as_of": "2026-11-17T22:00:00Z"},
        season={**SEASON, "as_of": "2026-11-18T04:00:00Z"},
        captured_at=MOMENT,
        timezone="Europe/Paris",
    )
    assert row.source_as_of == datetime(2026, 11, 17, 22, 0, tzinfo=UTC)


def test_source_as_of_is_null_without_any_timestamp() -> None:
    row = map_team_snapshot(
        team_external_id="t-1",
        elo={},
        stats={},
        season={},
        captured_at=MOMENT,
        timezone="Europe/Paris",
    )
    assert row.source_as_of is None
    assert row.elo_rating is None
    assert row.home_wins is None


def test_aberrant_values_become_null_with_a_warning() -> None:
    row = map_team_snapshot(
        team_external_id="t-1",
        elo={**ELO, "elo_rating": "fort"},
        stats={
            **STATS,
            "btts_rate": 1.5,
            "over_2_5_rate": -0.2,
            "goals_scored": -3,
            "matches_played": "beaucoup",
        },
        season={"home_away_splits": {"home": {"wins": -1, "ties": 2, "losses": 0}}},
        captured_at=MOMENT,
        timezone="Europe/Paris",
    )
    assert row.elo_rating is None
    assert row.btts_rate is None
    assert row.over_2_5_rate is None
    assert row.goals_scored is None
    assert row.matches_played is None
    assert row.home_wins is None
    assert row.home_draws == 2
    assert any("hors bornes" in warning for warning in row.warnings)
    assert any("négatif" in warning for warning in row.warnings)


def test_form_string_is_truncated_to_ten_characters() -> None:
    row = map_team_snapshot(
        team_external_id="t-1",
        elo=ELO,
        stats={**STATS, "form_string": "WWWWWWWWWWWWW"},
        season=SEASON,
        captured_at=MOMENT,
        timezone="Europe/Paris",
    )
    assert row.form_string == "WWWWWWWWWW"
    assert any("tronqué" in warning for warning in row.warnings)


def test_captured_on_uses_paris_time() -> None:
    late = datetime(2026, 11, 18, 23, 30, tzinfo=UTC)
    row = map_team_snapshot(
        team_external_id="t-1",
        elo=ELO,
        stats=STATS,
        season=SEASON,
        captured_at=late,
        timezone="Europe/Paris",
    )
    # 23:30 UTC le 18 novembre = 00:30 le 19 novembre à Paris.
    assert row.captured_on == date(2026, 11, 19)


# --- Service ---------------------------------------------------------------


def test_pass_writes_one_row_per_team(engine, seeded: None) -> None:
    with Session(engine) as db:
        _team(db, "t-1", "Alpha")
        _team(db, "t-2", "Beta")
        client = FakeSnapshotClient()

        report = run_snapshots(db, now=MOMENT, client=client)
        db.commit()

        assert report.status == "applied"
        assert report.teams.selected == 2
        assert report.teams.created == 2
        assert report.teams.written == 2
        assert report.requests == 7  # 2 fois 3 appels + 1 vérification du quota
        assert client.calls == [
            "elo:t-1",
            "stats:t-1",
            "season:t-1",
            "elo:t-2",
            "stats:t-2",
            "season:t-2",
            "usage",
        ]

        rows = db.scalars(select(TeamSnapshot).order_by(TeamSnapshot.captured_on)).all()
        assert len(rows) == 2
        row = next(item for item in rows if item.elo_rating == Decimal("1451"))
        assert row.captured_on == DAY
        assert _utc(row.captured_at) == MOMENT
        assert row.elo_games_counted == 44
        assert row.elo_last_match_date == date(2026, 11, 7)
        assert row.matches_played == 118
        assert row.btts_rate == Decimal("0.551")
        assert row.home_draws == 1
        assert row.away_draws == 0
        assert _utc(row.source_as_of) == datetime(2026, 11, 10, 6, 3, 18, 248000, tzinfo=UTC)


def test_second_pass_same_day_makes_no_call_and_no_row(engine, seeded: None) -> None:
    with Session(engine) as db:
        _team(db, "t-1", "Alpha")
        _team(db, "t-2", "Beta")
        run_snapshots(db, now=MOMENT, client=FakeSnapshotClient())
        db.commit()

        replay = FakeSnapshotClient()
        report = run_snapshots(db, now=MOMENT, client=replay)
        db.commit()

        assert report.status == "applied"
        assert report.teams.skipped == 2
        assert report.teams.created == 0
        assert report.requests == 0
        assert replay.calls == []
        assert db.scalar(select(func.count()).select_from(TeamSnapshot)) == 2


def test_force_updates_in_place_without_duplicate(engine, seeded: None) -> None:
    with Session(engine) as db:
        _team(db, "t-1", "Alpha")
        run_snapshots(db, now=MOMENT, client=FakeSnapshotClient())
        db.commit()

        changed = FakeSnapshotClient(
            elo={**ELO, "elo_rating": 1490},
            stats={**STATS, "btts_rate": 0.600},
        )
        report = run_snapshots(db, now=MOMENT, client=changed, force=True)
        db.commit()

        assert report.teams.created == 0
        assert report.teams.updated == 1
        assert db.scalar(select(func.count()).select_from(TeamSnapshot)) == 1
        row = db.scalar(select(TeamSnapshot))
        assert row is not None
        assert row.elo_rating == Decimal("1490")
        assert row.btts_rate == Decimal("0.600")


def test_a_null_never_overwrites_a_known_value(engine, seeded: None) -> None:
    with Session(engine) as db:
        _team(db, "t-1", "Alpha")
        run_snapshots(db, now=MOMENT, client=FakeSnapshotClient())
        db.commit()

        report = run_snapshots(
            db,
            now=MOMENT,
            client=FakeSnapshotClient(elo={}, stats={}, season={}),
            force=True,
        )
        db.commit()

        assert report.teams.unchanged == 1
        row = db.scalar(select(TeamSnapshot))
        assert row is not None
        assert row.elo_rating == Decimal("1451")
        assert row.btts_rate == Decimal("0.551")
        assert row.home_wins == 2


def test_budget_exhausted_stops_cleanly_as_partial(engine, seeded: None) -> None:
    with Session(engine) as db:
        _team(db, "t-1", "Alpha")
        _team(db, "t-2", "Beta")
        usage = get_usage(db, "bigballsdata", MOMENT)
        usage.limit = 3
        db.commit()

        report = run_snapshots(db, now=MOMENT, client=FakeSnapshotClient())
        db.commit()

        assert report.status == "partial"
        assert report.error is not None and "Budget insuffisant" in report.error
        assert db.scalar(select(func.count()).select_from(TeamSnapshot)) == 1


def test_auth_error_stops_immediately(engine, seeded: None) -> None:
    class AuthFailing(FakeSnapshotClient):
        def get_team_elo(self, team_id: str) -> Any:
            self.calls.append(f"elo:{team_id}")
            raise ProviderAuthError("La clé du fournisseur est refusée.")

    with Session(engine) as db:
        _team(db, "t-1", "Alpha")
        _team(db, "t-2", "Beta")
        client = AuthFailing()

        report = run_snapshots(db, now=MOMENT, client=client)
        db.commit()

        assert report.status == "failed"
        assert report.error is not None and "refusée" in report.error
        assert client.calls == ["elo:t-1"]
        assert db.scalar(select(func.count()).select_from(TeamSnapshot)) == 0
        run_row = db.scalar(select(SyncRun))
        assert run_row is not None and run_row.status == "failed"


def test_rate_limit_stops_cleanly_as_partial(engine, seeded: None) -> None:
    class RateLimited(FakeSnapshotClient):
        def get_team_stats(self, team_id: str) -> Any:
            self.calls.append(f"stats:{team_id}")
            raise ProviderRateLimitError("Le quota du fournisseur est épuisé.")

    with Session(engine) as db:
        _team(db, "t-1", "Alpha")
        _team(db, "t-2", "Beta")

        report = run_snapshots(db, now=MOMENT, client=RateLimited())
        db.commit()

        assert report.status == "partial"
        assert report.error is not None and "épuisé" in report.error
        assert db.scalar(select(func.count()).select_from(TeamSnapshot)) == 0


def test_missing_elo_still_writes_a_partial_row(engine, seeded: None) -> None:
    class EloMissing(FakeSnapshotClient):
        def get_team_elo(self, team_id: str) -> Any:
            self.calls.append(f"elo:{team_id}")
            if team_id == "t-1":
                raise ConnectorError("Le fournisseur a refusé la requête (404).")
            return self.elo

    with Session(engine) as db:
        _team(db, "t-1", "Alpha")
        _team(db, "t-2", "Beta")

        report = run_snapshots(db, now=MOMENT, client=EloMissing())
        db.commit()

        assert report.status == "applied"
        assert report.teams.partial == 1
        assert report.teams.written == 2
        row = db.scalar(
            select(TeamSnapshot)
            .join(Team, TeamSnapshot.team_id == Team.id)
            .where(Team.external_id == "t-1")
        )
        assert row is not None
        assert row.elo_rating is None
        assert row.btts_rate == Decimal("0.551")
        assert any("Alpha" in warning and "Elo" in warning for warning in report.teams.warnings)


def test_pass_without_any_team_is_empty(engine, seeded: None) -> None:
    with Session(engine) as db:
        report = run_snapshots(db, now=MOMENT, client=FakeSnapshotClient())
        db.commit()

        assert report.status == "empty"
        assert report.requests == 0
        assert db.scalar(select(func.count()).select_from(SyncRun)) == 0


# --- Sélection et journal --------------------------------------------------


def _competition_with_season(db: Session, code: str, name: str) -> Season:
    sport = db.scalar(select(Sport).where(Sport.code == "football"))
    assert sport is not None
    competition = Competition(sport_id=sport.id, name=name, code=code)
    db.add(competition)
    db.flush()
    season = Season(competition_id=competition.id, label="2026-2027", is_current=True)
    db.add(season)
    db.commit()
    return season


def _match(db: Session, season: Season, home: Team, away: Team) -> None:
    db.add(
        Match(
            season_id=season.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=MOMENT,
            status=MatchStatus.PROGRAMME,
        )
    )
    db.commit()


def test_leagues_option_restricts_teams_to_current_season(engine, seeded: None) -> None:
    with Session(engine) as db:
        alpha = _team(db, "t-1", "Alpha")
        beta = _team(db, "t-2", "Beta")
        alone = _team(db, "t-3", "Gamma")
        season = _competition_with_season(db, "ligue1", "Ligue 1")
        _match(db, season, alpha, beta)
        assert alone.external_id == "t-3"

        client = FakeSnapshotClient()
        report = run_snapshots(db, leagues=["ligue1"], now=MOMENT, client=client)
        db.commit()

        assert report.teams.selected == 2
        assert all("t-3" not in call for call in client.calls)
        assert db.scalar(select(func.count()).select_from(TeamSnapshot)) == 2


def test_pass_is_logged_without_any_secret(
    engine, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "bigballsdata_key", SECRET)
    with Session(engine) as db:
        _team(db, "t-1", "Alpha")

        report = run_snapshots(db, now=MOMENT, client=FakeSnapshotClient())
        db.commit()

        run_row = db.scalar(select(SyncRun))
        assert run_row is not None
        assert run_row.provider == "bigballsdata"
        assert run_row.operation == "snapshots"
        assert run_row.status == "applied"
        assert run_row.params["league"] == "toutes"
        assert run_row.credits_used == 0
        assert run_row.requests_used == 4  # 3 appels + vérification du quota
        assert run_row.summary["equipes"]["ecrites"] == 1

        payload = json.dumps(
            {"report": report.as_dict(), "params": run_row.params, "summary": run_row.summary},
            default=str,
        )
        assert SECRET not in payload


# --- Quota -----------------------------------------------------------------


def test_usage_response_recalibrates_the_local_quota(engine, seeded: None) -> None:
    with Session(engine) as db:
        _team(db, "t-1", "Alpha")

        report = run_snapshots(db, now=MOMENT, client=FakeSnapshotClient(usage={"remaining": 1200}))
        db.commit()

        usage = get_usage(db, "bigballsdata", MOMENT)
        assert usage.used == 4
        assert usage.limit == 1204
        assert report.quota_remaining == 1200


def test_usage_remaining_today_is_understood(engine, seeded: None) -> None:
    with Session(engine) as db:
        _team(db, "t-1", "Alpha")

        run_snapshots(
            db,
            now=MOMENT,
            client=FakeSnapshotClient(usage={"remaining_today": 500}),
        )
        db.commit()

        usage = get_usage(db, "bigballsdata", MOMENT)
        assert usage.used == 4
        assert usage.limit == 504


def test_usage_never_raises_the_project_budget(engine, seeded: None) -> None:
    # Le fournisseur annonce 2 000 par jour : notre plafond de 1 800 reste la règle.
    with Session(engine) as db:
        _team(db, "t-1", "Alpha")

        run_snapshots(
            db,
            now=MOMENT,
            client=FakeSnapshotClient(usage={"remaining_today": 1970}),
        )
        db.commit()

        usage = get_usage(db, "bigballsdata", MOMENT)
        assert usage.used == 4
        assert usage.limit == settings.bigballsdata_daily_budget


def test_unreadable_usage_keeps_the_local_counter(engine, seeded: None) -> None:
    with Session(engine) as db:
        _team(db, "t-1", "Alpha")

        report = run_snapshots(db, now=MOMENT, client=FakeSnapshotClient(usage={}))
        db.commit()

        assert report.status == "applied"
        assert any("illisible" in warning for warning in report.warnings)
        assert report.quota_remaining == settings.bigballsdata_daily_budget - 4


def test_failed_usage_check_never_fails_the_pass(engine, seeded: None) -> None:
    class UsageFailing(FakeSnapshotClient):
        def get_usage(self) -> Any:
            self.calls.append("usage")
            raise ConnectorError("Le fournisseur est injoignable.")

    with Session(engine) as db:
        _team(db, "t-1", "Alpha")

        report = run_snapshots(db, now=MOMENT, client=UsageFailing())
        db.commit()

        assert report.status == "applied"
        assert any("indisponible" in warning for warning in report.warnings)


# --- Client HTTP -----------------------------------------------------------


def test_client_exposes_snapshot_endpoints() -> None:
    seen: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, dict(request.url.params)))
        if request.url.path == "/v1/usage":
            return httpx.Response(200, json={"data": {"remaining": 1200}})
        if request.url.path.endswith("/elo"):
            return httpx.Response(200, json={"data": {"elo_rating": 1451}})
        if request.url.path.endswith("/stats"):
            return httpx.Response(200, json={"data": {"btts_rate": 0.55}})
        if request.url.path.endswith("/season"):
            return httpx.Response(200, json={"data": {"home_away_splits": {}}})
        if request.url.path == "/v1/games":
            return httpx.Response(200, json={"data": {"games": [{"game_id": "g-1"}], "total": 1}})
        return httpx.Response(404)

    with HttpClient(transport=httpx.MockTransport(handler)) as http:
        client = BigBallsDataClient(
            api_key="cle-de-test",
            base_url="https://api.example.test",
            http=http,
        )
        assert client.get_team_elo("t-1") == {"elo_rating": 1451}
        assert client.get_team_stats("t-1") == {"btts_rate": 0.55}
        assert client.get_team_season("t-1") == {"home_away_splits": {}}
        assert client.list_games(league="ligue1", day="2026-11-21") == [{"game_id": "g-1"}]
        assert client.get_usage() == {"remaining": 1200}

    paths = [path for path, _ in seen]
    assert paths == [
        "/v1/teams/t-1/elo",
        "/v1/teams/t-1/stats",
        "/v1/teams/t-1/season",
        "/v1/games",
        "/v1/usage",
    ]
    assert seen[1][1] == {"sport": "football"}
    assert seen[2][1] == {"sport": "football"}
    assert seen[3][1] == {"sport": "football", "league": "ligue1", "date": "2026-11-21"}
