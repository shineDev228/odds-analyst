"""Schéma des snapshots quotidiens (phase 14A.1).

Ces tests vérifient les garanties structurelles dont dépendent les collecteurs :
une ligne par équipe et par jour, deux créneaux conservés pour le board, et
aucune valeur aberrante acceptée silencieusement.
"""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from app.db.base import Base
from app.models import MarketBoardSnapshot, StandingsSnapshot, TeamSnapshot
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

DAY = date(2026, 11, 14)
CAPTURED_AT = datetime(2026, 11, 14, 6, 30, tzinfo=UTC)


def test_snapshot_tables_are_registered() -> None:
    names = set(Base.metadata.tables)
    assert {
        "team_snapshots",
        "standings_snapshots",
        "market_board_snapshots",
    } <= names


def test_team_snapshot_is_unique_per_day(session_factory) -> None:
    team_id = uuid4()
    with session_factory() as db:
        db.add(TeamSnapshot(team_id=team_id, captured_on=DAY, captured_at=CAPTURED_AT))
        db.commit()

    with session_factory() as db:
        db.add(TeamSnapshot(team_id=team_id, captured_on=DAY, captured_at=CAPTURED_AT))
        with pytest.raises(IntegrityError):
            db.commit()


def test_team_snapshot_accepts_a_new_day(session_factory) -> None:
    team_id = uuid4()
    with session_factory() as db:
        db.add(TeamSnapshot(team_id=team_id, captured_on=DAY, captured_at=CAPTURED_AT))
        db.add(
            TeamSnapshot(
                team_id=team_id,
                captured_on=date(2026, 11, 15),
                captured_at=CAPTURED_AT,
            )
        )
        db.commit()
        count = db.scalar(select(func.count()).select_from(TeamSnapshot))
    assert count == 2


def test_team_snapshot_rejects_a_rate_above_one(session_factory) -> None:
    with session_factory() as db:
        db.add(
            TeamSnapshot(
                team_id=uuid4(),
                captured_on=DAY,
                captured_at=CAPTURED_AT,
                btts_rate=1.5,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_market_board_keeps_both_slots(session_factory) -> None:
    match_id = uuid4()
    with session_factory() as db:
        for slot in ("morning", "evening"):
            db.add(
                MarketBoardSnapshot(
                    match_id=match_id,
                    external_match_id="match-1",
                    captured_on=DAY,
                    snapshot_slot=slot,
                    captured_at=CAPTURED_AT,
                    home_decimal=2.1,
                )
            )
        db.commit()
        count = db.scalar(select(func.count()).select_from(MarketBoardSnapshot))
    assert count == 2


def test_market_board_rejects_an_unknown_slot(session_factory) -> None:
    with session_factory() as db:
        db.add(
            MarketBoardSnapshot(
                match_id=uuid4(),
                external_match_id="match-1",
                captured_on=DAY,
                snapshot_slot="midi",
                captured_at=CAPTURED_AT,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_standings_snapshot_is_unique_per_team_and_season(session_factory) -> None:
    team_id = uuid4()
    season_id = uuid4()
    competition_id = uuid4()
    with session_factory() as db:
        for _ in range(2):
            db.add(
                StandingsSnapshot(
                    competition_id=competition_id,
                    season_id=season_id,
                    team_id=team_id,
                    captured_on=DAY,
                    rank=1,
                    points=30,
                )
            )
        with pytest.raises(IntegrityError):
            db.commit()
