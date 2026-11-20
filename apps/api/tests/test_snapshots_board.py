"""Tests du board marché BigBallsData (phase 14A, étape 4).

Aucun appel réseau : le service reçoit un client simulé. Les formes de réponse
reproduisent le relevé réel du 21/11/2026 (cotes parfois `null`, un seul côté,
une seule ligne de total).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from app.connectors.base import ConnectorError, ProviderAuthError
from app.connectors.bigballsdata.snapshot_mapping import map_market_board_snapshot
from app.connectors.quota import get_usage
from app.core.config import settings
from app.models.connector import SyncRun
from app.models.match import Match, MatchStatus
from app.models.reference import Competition, Season, Sport, Team
from app.models.snapshot import MarketBoardSnapshot, TeamSnapshot
from app.services.snapshots import run_snapshots
from sqlalchemy import func, select
from sqlalchemy.orm import Session

MOMENT = datetime(2026, 11, 18, 5, 30, tzinfo=UTC)
DAY = date(2026, 11, 18)
GAME_ID = "2f7f4dc6-71c4-4468-b2b6-1ce91922344a"
KICKOFF = "2026-11-21T19:45:00.000Z"

ODDS = {
    "moneyline": {"home": 130, "away": 260},
    "total": {"line": 2.5, "over_juice": -112, "under_juice": -108},
    "books_count": 10,
    "odds_updated_at": "2026-11-18T11:33:27.469Z",
}


def _game(
    game_id: str = GAME_ID,
    *,
    status: str = "upcoming",
    scheduled_at: str | None = KICKOFF,
    odds: Any = ODDS,
) -> dict[str, Any]:
    return {
        "game_id": game_id,
        "status": status,
        "scheduled_at": scheduled_at,
        "odds": odds,
    }


class FakeBoardClient:
    """Client BigBallsData simulé, limité au board et au quota."""

    provider = "bigballsdata"

    def __init__(
        self,
        games: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
        *,
        usage: Any = None,
    ) -> None:
        self.games = games or {}
        self.usage = {"remaining": 1200} if usage is None else usage
        self.calls: list[str] = []

    def list_games(self, *, league: str, day: str) -> list[dict[str, Any]]:
        self.calls.append(f"{league}:{day}")
        return self.games.get((league, day), [])

    def get_usage(self) -> Any:
        self.calls.append("usage")
        return self.usage


def _match(db: Session, external_id: str = GAME_ID) -> Match:
    sport = db.scalar(select(Sport).where(Sport.code == "football"))
    assert sport is not None
    competition = Competition(sport_id=sport.id, name="Ligue 1", code="ligue1")
    db.add(competition)
    db.flush()
    season = Season(competition_id=competition.id, label="2026-2027", is_current=True)
    db.add(season)
    db.flush()
    home = Team(sport_id=sport.id, name="Nice", external_id="team-nice")
    away = Team(sport_id=sport.id, name="Paris SG", external_id="team-psg")
    db.add_all([home, away])
    db.flush()
    match = Match(
        external_id=external_id,
        season_id=season.id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_at=datetime(2026, 11, 21, 19, 45, tzinfo=UTC),
        status=MatchStatus.PROGRAMME,
    )
    db.add(match)
    db.commit()
    return match


def run_board(
    db: Session,
    client: FakeBoardClient,
    *,
    slot: str = "morning",
    now: datetime = MOMENT,
    leagues: list[str] | None = None,
    **options: Any,
) -> Any:
    return run_snapshots(
        db,
        leagues=leagues if leagues is not None else ["ligue1"],
        slot=slot,
        include_teams=False,
        include_board=True,
        now=now,
        client=client,
        **options,
    )


# --- Normalisation ---------------------------------------------------------


def test_board_mapping_reads_prices_and_metadata() -> None:
    row = map_market_board_snapshot(
        game=_game(),
        slot="evening",
        captured_at=MOMENT,
        timezone="Europe/Paris",
    )
    assert row.external_match_id == GAME_ID
    assert row.snapshot_slot == "evening"
    assert row.captured_on == DAY
    assert row.status == "upcoming"
    assert row.scheduled_at == datetime(2026, 11, 21, 19, 45, tzinfo=UTC)
    assert row.home_decimal == Decimal("2.300")
    assert row.away_decimal == Decimal("3.600")
    assert row.total_line == Decimal("2.5")
    assert row.over_decimal == Decimal("1.893")
    assert row.under_decimal == Decimal("1.926")
    assert row.books_count == 10
    assert row.odds_updated_at == datetime(2026, 11, 18, 11, 33, 27, 469000, tzinfo=UTC)
    assert row.has_values is True


def test_board_mapping_converts_american_odds() -> None:
    row = map_market_board_snapshot(
        game=_game(
            odds={
                "moneyline": {"home": 114, "away": 2242},
                "total": {"line": 2.5, "over_juice": -112, "under_juice": 104},
            }
        ),
        slot="morning",
        captured_at=MOMENT,
        timezone="Europe/Paris",
    )
    assert row.home_decimal == Decimal("2.140")
    assert row.away_decimal == Decimal("23.420")
    assert row.over_decimal == Decimal("1.893")
    assert row.under_decimal == Decimal("2.040")
    assert row.warnings == []


def test_board_mapping_keeps_a_decimal_price() -> None:
    # Le fournisseur mélange les écritures : 2,25 est déjà décimal.
    row = map_market_board_snapshot(
        game=_game(odds={**ODDS, "moneyline": {"home": 2.25, "away": 3.0}}),
        slot="morning",
        captured_at=MOMENT,
        timezone="Europe/Paris",
    )
    assert row.home_decimal == Decimal("2.250")
    assert row.away_decimal == Decimal("3.000")
    assert row.warnings == []


def test_board_mapping_rejects_a_price_at_or_below_one() -> None:
    row = map_market_board_snapshot(
        game=_game(odds={**ODDS, "moneyline": {"home": 0.95, "away": 3.0}}),
        slot="morning",
        captured_at=MOMENT,
        timezone="Europe/Paris",
    )
    assert row.home_decimal is None
    assert row.away_decimal == Decimal("3.000")
    assert any("hors format" in warning for warning in row.warnings)


def test_board_mapping_rejects_an_unknown_slot() -> None:
    with pytest.raises(ValueError):
        map_market_board_snapshot(
            game=_game(), slot="midi", captured_at=MOMENT, timezone="Europe/Paris"
        )


def test_board_mapping_keeps_a_missing_side_null() -> None:
    row = map_market_board_snapshot(
        game=_game(odds={**ODDS, "moneyline": {"home": 130, "away": None}}),
        slot="morning",
        captured_at=MOMENT,
        timezone="Europe/Paris",
    )
    assert row.home_decimal == Decimal("2.300")
    assert row.away_decimal is None


# --- Écriture --------------------------------------------------------------


def test_board_writes_a_morning_row(engine, seeded: None) -> None:
    with Session(engine) as db:
        _match(db)
        client = FakeBoardClient({("ligue1", "2026-11-18"): [_game()]})

        report = run_board(db, client)
        db.commit()

        assert report.status == "applied"
        assert report.board.received == 1
        assert report.board.matched == 1
        assert report.board.created == 1
        assert report.requests == 3  # 2 fenêtres + 1 vérification du quota
        assert client.calls == ["ligue1:2026-11-18", "ligue1:2026-11-19", "usage"]

        row = db.scalar(select(MarketBoardSnapshot))
        assert row is not None
        assert row.match_id is not None
        assert row.external_match_id == GAME_ID
        assert row.captured_on == DAY
        assert row.snapshot_slot == "morning"
        assert row.home_decimal == Decimal("2.300")
        assert row.away_decimal == Decimal("3.600")
        assert row.total_line == Decimal("2.5")
        assert row.over_decimal == Decimal("1.893")
        assert row.under_decimal == Decimal("1.926")
        assert row.books_count == 10
        assert row.odds_updated_at is not None


def test_board_without_odds_writes_no_row(engine, seeded: None) -> None:
    with Session(engine) as db:
        _match(db)
        client = FakeBoardClient({("ligue1", "2026-11-18"): [_game(odds=None)]})

        report = run_board(db, client)
        db.commit()

        assert report.board.no_odds == 1
        assert report.board.written == 0
        assert db.scalar(select(func.count()).select_from(MarketBoardSnapshot)) == 0


def test_board_with_a_missing_side_writes_a_null(engine, seeded: None) -> None:
    with Session(engine) as db:
        _match(db)
        client = FakeBoardClient(
            {("ligue1", "2026-11-18"): [_game(odds={**ODDS, "moneyline": {"home": 130}})]}
        )

        report = run_board(db, client)
        db.commit()

        assert report.board.created == 1
        row = db.scalar(select(MarketBoardSnapshot))
        assert row is not None
        assert row.home_decimal == Decimal("2.300")
        assert row.away_decimal is None


def test_board_ignores_a_started_game(engine, seeded: None) -> None:
    with Session(engine) as db:
        _match(db)
        client = FakeBoardClient(
            {("ligue1", "2026-11-18"): [_game(scheduled_at="2026-11-18T05:00:00Z")]}
        )

        report = run_board(db, client)
        db.commit()

        assert report.board.too_late == 1
        assert report.board.written == 0
        assert db.scalar(select(func.count()).select_from(MarketBoardSnapshot)) == 0


def test_board_ignores_a_non_upcoming_game(engine, seeded: None) -> None:
    with Session(engine) as db:
        _match(db)
        client = FakeBoardClient({("ligue1", "2026-11-18"): [_game(status="finished")]})

        report = run_board(db, client)
        db.commit()

        assert report.board.not_upcoming == 1
        assert report.board.written == 0


def test_board_never_creates_an_unknown_match(engine, seeded: None) -> None:
    with Session(engine) as db:
        _match(db)
        client = FakeBoardClient(
            {("ligue1", "2026-11-18"): [_game(game_id="rencontre-inconnue")]}
        )

        report = run_board(db, client)
        db.commit()

        assert report.board.unmatched == 1
        assert report.board.written == 0
        assert db.scalar(select(func.count()).select_from(Match)) == 1


def test_board_with_no_valid_price_writes_no_row(engine, seeded: None) -> None:
    with Session(engine) as db:
        _match(db)
        invalid = {
            "moneyline": {"home": 0.5, "away": -20},
            "total": {"line": -1, "over_juice": "x", "under_juice": None},
            "books_count": -2,
        }
        client = FakeBoardClient({("ligue1", "2026-11-18"): [_game(odds=invalid)]})

        report = run_board(db, client)
        db.commit()

        assert report.board.no_values == 1
        assert report.board.written == 0
        assert any("hors format" in warning for warning in report.board.warnings)
        assert db.scalar(select(func.count()).select_from(MarketBoardSnapshot)) == 0


def test_morning_and_evening_coexist(engine, seeded: None) -> None:
    with Session(engine) as db:
        _match(db)
        games = {("ligue1", "2026-11-18"): [_game()]}

        morning = run_board(db, FakeBoardClient(games), slot="morning")
        db.commit()
        evening = run_board(db, FakeBoardClient(games), slot="evening")
        db.commit()

        assert morning.board.created == 1
        assert evening.board.created == 1
        rows = db.scalars(
            select(MarketBoardSnapshot).order_by(MarketBoardSnapshot.snapshot_slot)
        ).all()
        assert [row.snapshot_slot for row in rows] == ["evening", "morning"]
        # Le relevé du soir ne remplace jamais celui du matin.
        assert db.scalar(select(func.count()).select_from(MarketBoardSnapshot)) == 2


def test_same_slot_replay_updates_in_place(engine, seeded: None) -> None:
    with Session(engine) as db:
        _match(db)
        first = {("ligue1", "2026-11-18"): [_game()]}
        run_board(db, FakeBoardClient(first), slot="morning")
        db.commit()

        moved = {
            "moneyline": {"home": 105, "away": 320},
            "total": {"line": 2.5, "over_juice": -110, "under_juice": -105},
            "books_count": 9,
            "odds_updated_at": "2026-11-18T11:40:00Z",
        }
        second = {("ligue1", "2026-11-18"): [_game(odds=moved)]}
        report = run_board(db, FakeBoardClient(second), slot="morning")
        db.commit()

        assert report.board.created == 0
        assert report.board.updated == 1
        assert db.scalar(select(func.count()).select_from(MarketBoardSnapshot)) == 1
        row = db.scalar(select(MarketBoardSnapshot))
        assert row is not None
        assert row.home_decimal == Decimal("2.050")
        assert row.away_decimal == Decimal("4.200")
        assert row.books_count == 9


def test_board_only_pass_does_not_touch_team_snapshots(engine, seeded: None) -> None:
    with Session(engine) as db:
        _match(db)
        client = FakeBoardClient({("ligue1", "2026-11-18"): [_game()]})

        run_board(db, client)
        db.commit()

        assert db.scalar(select(func.count()).select_from(TeamSnapshot)) == 0


def test_combined_pass_collects_teams_and_board(engine, seeded: None) -> None:
    class CombinedClient(FakeBoardClient):
        def get_team_elo(self, team_id: str) -> dict[str, Any]:
            self.calls.append(f"elo:{team_id}")
            return {"elo_rating": 1451, "last_computed": "2026-11-10T06:03:18Z"}

        def get_team_stats(self, team_id: str) -> dict[str, Any]:
            self.calls.append(f"stats:{team_id}")
            return {"matches_played": 10, "btts_rate": 0.5, "as_of": "2026-11-18T05:00:00Z"}

        def get_team_season(self, team_id: str) -> dict[str, Any]:
            self.calls.append(f"season:{team_id}")
            return {
                "as_of": "2026-11-18T05:00:00Z",
                "home_away_splits": {"home": {"wins": 2, "ties": 1, "losses": 0}},
            }

    with Session(engine) as db:
        _match(db)
        client = CombinedClient({("ligue1", "2026-11-18"): [_game()]})

        report = run_snapshots(
            db,
            leagues=["ligue1"],
            slot="morning",
            include_teams=True,
            include_board=True,
            now=MOMENT,
            client=client,
        )
        db.commit()

        assert report.status == "applied"
        assert report.teams.created == 2
        assert report.board.created == 1
        assert report.requests == 9  # 6 appels équipes + 2 fenêtres + quota
        assert db.scalar(select(func.count()).select_from(TeamSnapshot)) == 2
        assert db.scalar(select(func.count()).select_from(MarketBoardSnapshot)) == 1
        run_row = db.scalar(select(SyncRun))
        assert run_row is not None
        assert run_row.summary["equipes"]["ecrites"] == 2
        assert run_row.summary["board"]["ecrites"] == 1
        assert run_row.requests_used == 9


# --- Fenêtre, budget et pannes ---------------------------------------------


def test_board_window_is_j_and_j_plus_one_in_utc(engine, seeded: None) -> None:
    with Session(engine) as db:
        client = FakeBoardClient()

        run_board(db, client)
        db.commit()

        assert client.calls[:2] == ["ligue1:2026-11-18", "ligue1:2026-11-19"]


def test_board_budget_exhausted_is_partial(engine, seeded: None) -> None:
    with Session(engine) as db:
        usage = get_usage(db, "bigballsdata", MOMENT)
        usage.limit = 1
        db.commit()

        report = run_board(db, FakeBoardClient())
        db.commit()

        assert report.status == "partial"
        assert report.error is not None and "Budget insuffisant" in report.error
        assert report.requests == 1


def test_board_auth_error_fails_immediately(engine, seeded: None) -> None:
    class AuthFailing(FakeBoardClient):
        def list_games(self, *, league: str, day: str) -> list[dict[str, Any]]:
            self.calls.append(f"{league}:{day}")
            raise ProviderAuthError("La clé du fournisseur est refusée.")

    with Session(engine) as db:
        client = AuthFailing()

        report = run_board(db, client)
        db.commit()

        assert report.status == "failed"
        assert report.error is not None and "refusée" in report.error
        assert client.calls == ["ligue1:2026-11-18"]
        run_row = db.scalar(select(SyncRun))
        assert run_row is not None and run_row.status == "failed"


def test_board_league_error_does_not_block_the_others(engine, seeded: None) -> None:
    class OneLeagueMissing(FakeBoardClient):
        def list_games(self, *, league: str, day: str) -> list[dict[str, Any]]:
            self.calls.append(f"{league}:{day}")
            if league == "mls":
                raise ConnectorError("Le fournisseur a refusé la requête (404).")
            return self.games.get((league, day), [])

    with Session(engine) as db:
        _match(db)
        client = OneLeagueMissing({("ligue1", "2026-11-18"): [_game()]})

        report = run_board(db, client, leagues=["ligue1", "mls"])
        db.commit()

        assert report.status == "applied"
        assert any("mls" in warning for warning in report.board.warnings)
        assert report.board.written == 1


# --- Journal ---------------------------------------------------------------


def test_board_pass_is_logged_without_secret(
    engine, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "cle-secrete-board-jamais-journalisee"
    monkeypatch.setattr(settings, "bigballsdata_key", secret)
    with Session(engine) as db:
        _match(db)
        client = FakeBoardClient({("ligue1", "2026-11-18"): [_game()]})

        report = run_board(db, client, slot="evening", facts_standings=158)
        db.commit()

        run_row = db.scalar(select(SyncRun))
        assert run_row is not None
        assert run_row.operation == "snapshots"
        assert run_row.params["slot"] == "evening"
        assert run_row.params["league"] == "ligue1"
        assert run_row.summary["classements"] == 158
        assert run_row.summary["board"]["ecrites"] == 1
        assert run_row.summary["equipes"]["ecrites"] == 0
        assert run_row.credits_used == 0
        assert run_row.requests_used == 3
        payloads = json.dumps(
            {"report": report.as_dict(), "params": run_row.params, "summary": run_row.summary},
            default=str,
        )
        assert secret not in payloads
