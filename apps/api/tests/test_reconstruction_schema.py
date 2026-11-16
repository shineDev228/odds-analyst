"""Schéma de la reconstruction BigBallsData (phase 15, étape 1).

Ces tests vérifient les garanties structurelles dont dépendent les importeurs :
identifiants fournisseur uniques, une ligne CSV appliquée au plus une fois par
rencontre, un seul lien de cotes actif, et aucune valeur aberrante acceptée
silencieusement.
"""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from app.db.base import Base
from app.models import (
    Competition,
    CsvLink,
    Match,
    OddsEventLink,
    Season,
    Team,
    TeamMatchStats,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

KICKOFF = datetime(2026, 11, 20, 19, 45, tzinfo=UTC)
ROW_DATE = date(2026, 11, 8)


def _team(name: str, external_id: str | None = None) -> Team:
    return Team(sport_id=uuid4(), name=name, external_id=external_id)


def _match(external_id: str | None = None) -> Match:
    return Match(
        season_id=uuid4(),
        home_team_id=uuid4(),
        away_team_id=uuid4(),
        kickoff_at=KICKOFF,
        external_id=external_id,
    )


def _csv_link(**overrides) -> CsvLink:
    values = {
        "season_id": uuid4(),
        "row_key": f"F1:{ROW_DATE}:1-2:1-1",
        "row_date": ROW_DATE,
        "home_team_name": "Rennes",
        "away_team_name": "Lille",
        "home_score": 1,
        "away_score": 2,
        "half_time_home_score": 1,
        "half_time_away_score": 1,
    }
    values.update(overrides)
    return CsvLink(**values)


def _odds_link(**overrides) -> OddsEventLink:
    values = {
        "event_id": "evt-1",
        "match_id": uuid4(),
        "competition_code": "ligue1",
        "commence_at": KICKOFF,
        "home_team_name": "Lorient",
        "away_team_name": "Rennes",
        "is_active": True,
    }
    values.update(overrides)
    return OddsEventLink(**values)


def test_reconstruction_tables_are_registered() -> None:
    names = set(Base.metadata.tables)
    assert {"csv_links", "odds_event_links"} <= names


def test_new_columns_are_registered() -> None:
    tables = Base.metadata.tables
    assert "code" in tables["competitions"].columns
    assert "external_label" in tables["seasons"].columns
    assert {"external_id", "logo_url"} <= set(tables["teams"].columns.keys())
    assert {
        "external_id",
        "round_name",
        "broadcast",
        "attendance",
        "has_odds",
    } <= set(tables["matches"].columns.keys())
    assert {
        "shots_off_target",
        "blocked_shots",
        "shots_inside_box",
        "shots_outside_box",
        "fouls",
        "offsides",
        "goalkeeper_saves",
        "passes",
        "accurate_passes",
        "pass_percentage",
    } <= set(tables["team_match_stats"].columns.keys())


def test_team_external_id_is_unique(session_factory) -> None:
    with session_factory() as db:
        db.add(_team("Stade Brestois 29", external_id="bbd-team-1"))
        db.commit()

    with session_factory() as db:
        db.add(_team("Brest", external_id="bbd-team-1"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_team_external_id_accepts_several_nulls(session_factory) -> None:
    with session_factory() as db:
        db.add(_team("Équipe manuelle A"))
        db.add(_team("Équipe manuelle B"))
        db.commit()
        count = db.scalar(select(func.count()).select_from(Team))
    assert count == 2


def test_competition_code_is_unique(session_factory) -> None:
    with session_factory() as db:
        db.add(Competition(sport_id=uuid4(), name="Ligue 1", code="ligue1"))
        db.commit()

    with session_factory() as db:
        db.add(Competition(sport_id=uuid4(), name="Ligue 1 bis", code="ligue1"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_season_keeps_the_provider_label(session_factory) -> None:
    with session_factory() as db:
        db.add(
            Season(
                competition_id=uuid4(),
                label="2026-2027",
                external_label="2026",
            )
        )
        db.commit()
        stored = db.scalar(select(Season.external_label))
    assert stored == "2026"


def test_match_external_id_is_unique(session_factory) -> None:
    with session_factory() as db:
        db.add(_match(external_id="bbd-match-1"))
        db.commit()

    with session_factory() as db:
        db.add(_match(external_id="bbd-match-1"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_match_accepts_provider_details(session_factory) -> None:
    with session_factory() as db:
        db.add(
            Match(
                season_id=uuid4(),
                home_team_id=uuid4(),
                away_team_id=uuid4(),
                kickoff_at=KICKOFF,
                external_id="bbd-match-2",
                round_name="Journée 12",
                broadcast="Canal+",
                attendance=28000,
                has_odds=True,
            )
        )
        db.commit()
        stored = db.scalar(select(func.count()).select_from(Match))
    assert stored == 1


def test_match_rejects_negative_attendance(session_factory) -> None:
    with session_factory() as db:
        db.add(
            Match(
                season_id=uuid4(),
                home_team_id=uuid4(),
                away_team_id=uuid4(),
                kickoff_at=KICKOFF,
                attendance=-1,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_csv_link_row_is_unique_per_source(session_factory) -> None:
    with session_factory() as db:
        db.add(_csv_link())
        db.commit()

    with session_factory() as db:
        db.add(_csv_link())
        with pytest.raises(IntegrityError):
            db.commit()


def test_csv_link_is_applied_at_most_once_per_match(session_factory) -> None:
    match_id = uuid4()
    with session_factory() as db:
        db.add(
            _csv_link(
                match_id=match_id,
                status="applied",
                method="score",
                confidence=1.0,
                margin=0.72,
            )
        )
        db.commit()

    with session_factory() as db:
        db.add(
            _csv_link(
                row_key="F1:2026-11-09:0-0:0-0",
                match_id=match_id,
                status="applied",
                method="score",
                confidence=1.0,
                margin=1.0,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_csv_link_pending_does_not_claim_a_match(session_factory) -> None:
    with session_factory() as db:
        db.add(_csv_link(row_key="F1:2026-11-08:1-2:1-1", status="pending"))
        db.add(_csv_link(row_key="F1:2026-11-09:0-0:0-0", status="pending"))
        db.commit()
        count = db.scalar(select(func.count()).select_from(CsvLink))
    assert count == 2


def test_csv_link_applied_requires_a_match(session_factory) -> None:
    with session_factory() as db:
        db.add(_csv_link(status="applied", match_id=None))
        with pytest.raises(IntegrityError):
            db.commit()


def test_csv_link_rejects_an_unknown_status(session_factory) -> None:
    with session_factory() as db:
        db.add(_csv_link(status="peut-etre"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_odds_event_is_unique_per_provider(session_factory) -> None:
    with session_factory() as db:
        db.add(_odds_link(event_id="evt-42"))
        db.commit()

    with session_factory() as db:
        db.add(_odds_link(event_id="evt-42"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_odds_event_has_one_active_link_per_match(session_factory) -> None:
    match_id = uuid4()
    with session_factory() as db:
        db.add(_odds_link(event_id="evt-1", match_id=match_id, is_active=True))
        db.commit()

    with session_factory() as db:
        db.add(_odds_link(event_id="evt-2", match_id=match_id, is_active=True))
        with pytest.raises(IntegrityError):
            db.commit()


def test_odds_event_can_be_superseded(session_factory) -> None:
    match_id = uuid4()
    with session_factory() as db:
        db.add(_odds_link(event_id="evt-1", match_id=match_id, is_active=True))
        db.commit()

    with session_factory() as db:
        previous = db.scalar(select(OddsEventLink).where(OddsEventLink.event_id == "evt-1"))
        assert previous is not None
        previous.is_active = False
        db.add(_odds_link(event_id="evt-2", match_id=match_id, is_active=True))
        db.commit()
        count = db.scalar(
            select(func.count())
            .select_from(OddsEventLink)
            .where(OddsEventLink.match_id == match_id)
        )
    assert count == 2


def test_stats_accept_the_provider_columns(session_factory) -> None:
    with session_factory() as db:
        db.add(
            TeamMatchStats(
                match_id=uuid4(),
                team_id=uuid4(),
                is_home=True,
                shots=12,
                shots_on_target=5,
                shots_off_target=4,
                blocked_shots=3,
                shots_inside_box=8,
                shots_outside_box=4,
                fouls=11,
                offsides=2,
                corners=6,
                goalkeeper_saves=3,
                passes=520,
                accurate_passes=470,
                pass_percentage=90.4,
                possession=58.0,
            )
        )
        db.commit()
        stored = db.scalar(select(TeamMatchStats.pass_percentage))
    assert stored == pytest.approx(90.4)


def test_stats_reject_negative_counts(session_factory) -> None:
    with session_factory() as db:
        db.add(
            TeamMatchStats(
                match_id=uuid4(),
                team_id=uuid4(),
                is_home=True,
                shots_off_target=-1,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_stats_reject_a_pass_percentage_above_hundred(session_factory) -> None:
    with session_factory() as db:
        db.add(
            TeamMatchStats(
                match_id=uuid4(),
                team_id=uuid4(),
                is_home=True,
                pass_percentage=101.0,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
