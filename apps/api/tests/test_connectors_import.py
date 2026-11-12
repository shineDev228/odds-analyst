"""Tests d'intégration des connecteurs sur SQLite (aucun réseau)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from app.connectors.base import ConnectorError
from app.models.connector import ConnectorLink, ProviderRef, RefEntity, SyncRun
from app.models.market import Market, OddsSnapshot, Selection
from app.models.match import Match, MatchStatus, TeamMatchStats
from app.models.reference import Competition, Season, Sport, Team
from app.services import connectors as service
from sqlalchemy import func, select
from sqlalchemy.orm import Session

COMPETITION = "Ligue 1 Test"
SEASON = "2025-2026"

# Date de référence stable pour les tests : dans la fenêtre de 10 jours, et
# identique pour la rencontre interne et l'événement de cotes.
KICKOFF = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3)


def _require[T](value: T | None) -> T:
    """Réduit l'optionnel des lectures SQLAlchemy dans les tests."""
    assert value is not None
    return value


class FakeBigBalls:
    def __init__(self, matches: list[dict], stats: dict | None = None) -> None:
        self.matches = matches
        self.stats = stats or {}

    def list_matches(self, **_: object) -> list[dict]:
        return self.matches

    def get_statistics(self, match_id: str) -> dict:
        return self.stats.get(match_id, {})

    def close(self) -> None:
        return None


class FakeOdds:
    def __init__(self, events: list[dict], extended: dict | None = None) -> None:
        self.events = events
        self.extended = extended or {}

    def competition_odds(self, *_: object, **__: object) -> list[dict]:
        return self.events

    def event_odds(self, *_: object, **__: object) -> dict:
        event_id = str(_[1])
        return self.extended.get(event_id, {"id": event_id, "bookmakers": []})

    def close(self) -> None:
        return None


def _raw_match(
    external_id: str = "bbd-1",
    *,
    status: str = "scheduled",
    score: dict | None = None,
    kickoff: datetime | None = None,
) -> dict:
    moment = kickoff or KICKOFF
    return {
        "id": external_id,
        "kickoff_utc": moment.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "home": {"id": "bbd-h", "name": "Paris Saint-Germain", "short_name": "PSG"},
        "away": {"id": "bbd-a", "name": "RC Lens", "short_name": "RCL"},
        "score": score,
    }


def _setup(engine, provider: str = "bigballsdata") -> str:
    with Session(engine) as db:
        sport = _require(db.scalar(select(Sport).where(Sport.code == "football")))
        competition = Competition(sport_id=sport.id, name=COMPETITION)
        db.add(competition)
        db.flush()
        season = Season(competition_id=competition.id, label=SEASON, is_current=True)
        db.add(season)
        db.flush()
        link = ConnectorLink(
            provider=provider,
            competition_id=competition.id,
            season_id=season.id,
            external_league_id="ligue-1",
            external_season="2025",
        )
        db.add(link)
        db.commit()
        return str(link.id)


def _setup_internal_match(engine) -> tuple[str, str, str]:
    with Session(engine) as db:
        sport = _require(db.scalar(select(Sport).where(Sport.code == "football")))
        competition = Competition(sport_id=sport.id, name=COMPETITION)
        db.add(competition)
        db.flush()
        season = Season(competition_id=competition.id, label=SEASON, is_current=True)
        db.add(season)
        db.flush()
        home = Team(sport_id=sport.id, name="Paris Saint-Germain", short_name="PSG")
        away = Team(sport_id=sport.id, name="RC Lens", short_name="RCL")
        db.add_all([home, away])
        db.flush()
        kickoff = KICKOFF
        match = Match(
            season_id=season.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=kickoff,
            status=MatchStatus.PROGRAMME,
        )
        db.add(match)
        db.flush()
        link = ConnectorLink(
            provider="the_odds_api",
            competition_id=competition.id,
            season_id=season.id,
            external_league_id="soccer_france_ligue_one",
            external_season="2025",
        )
        db.add(link)
        db.commit()
        return str(match.id), str(link.id), str(season.id)


def _event(captured: str = "2026-11-10T09:30:00Z", bookmaker: str = "onexbet") -> dict:
    return {
        "id": "evt-1",
        "commence_time": KICKOFF.isoformat().replace("+00:00", "Z"),
        "home_team": "Paris Saint-Germain",
        "away_team": "RC Lens",
        "bookmakers": [
            {
                "key": bookmaker,
                "title": "1xBet",
                "last_update": captured,
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Paris Saint-Germain", "price": 1.55},
                            {"name": "Draw", "price": 4.2},
                            {"name": "RC Lens", "price": 6.1},
                        ],
                    },
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "point": 2.5, "price": 1.9},
                            {"name": "Under", "point": 2.5, "price": 1.92},
                        ],
                    },
                    {
                        "key": "double_chance",
                        "outcomes": [
                            {"name": "Paris Saint-Germain or Draw", "price": 1.2},
                            {"name": "Paris Saint-Germain or RC Lens", "price": 1.28},
                            {"name": "Draw or RC Lens", "price": 2.4},
                        ],
                    },
                    {
                        "key": "btts",
                        "outcomes": [
                            {"name": "Yes", "price": 1.75},
                            {"name": "No", "price": 2.05},
                        ],
                    },
                ],
            }
        ],
    }


@pytest.fixture()
def seeded_db(seeded: None, engine) -> None:
    return None


def test_fixtures_preview_writes_nothing_then_apply(engine, seeded_db, monkeypatch) -> None:
    _setup(engine)
    monkeypatch.setattr(
        service, "client_for", lambda *_, **__: FakeBigBalls([_raw_match()])
    )
    with Session(engine) as db:
        link = _require(db.scalar(select(ConnectorLink)))
        run = service.preview_fixtures(db, link)
        db.commit()
        assert run.summary["counts"]["created"] == 1
        assert db.scalar(select(func.count()).select_from(Match)) == 0

        counts = service.apply_preview(db, run)
        db.commit()
        assert counts.created == 1
        match = db.scalar(select(Match))
        assert match is not None
        assert match.data_source == "bigballsdata"
        assert match.status == MatchStatus.PROGRAMME
        refs = _require(db.scalar(select(func.count()).select_from(ProviderRef)))
        assert refs >= 3


def test_fixture_preview_is_idempotent_and_expires(engine, seeded_db, monkeypatch) -> None:
    _setup(engine)
    monkeypatch.setattr(
        service, "client_for", lambda *_, **__: FakeBigBalls([_raw_match()])
    )
    with Session(engine) as db:
        link = _require(db.scalar(select(ConnectorLink)))
        run = service.preview_fixtures(db, link)
        db.commit()
        service.apply_preview(db, run)
        db.commit()
        with pytest.raises(ConnectorError) as exc:
            service.apply_preview(db, run)
        assert exc.value.status_code == 409

        second = service.preview_fixtures(db, link)
        db.commit()
        assert second.summary["counts"]["unchanged"] == 1
        second.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
        with pytest.raises(ConnectorError) as expired:
            service.apply_preview(db, second)
        assert expired.value.status_code == 410


def test_manual_match_is_preserved(engine, seeded_db, monkeypatch) -> None:
    match_id, _, _ = _setup_internal_match(engine)
    monkeypatch.setattr(
        service,
        "client_for",
        lambda *_, **__: FakeBigBalls(
            [_raw_match("bbd-9", status="finished", score={"home": 2, "away": 1})]
        ),
    )
    with Session(engine) as db:
        match = _require(db.get(Match, UUID(match_id)))
        # La rencontre interne devient manuelle et porte déjà une valeur.
        match.data_source = "manual"
        match.home_score = 4
        match.away_score = 4
        competition = _require(
            db.scalar(select(Competition).where(Competition.name == COMPETITION))
        )
        season = _require(
            db.scalar(select(Season).where(Season.competition_id == competition.id))
        )
        link = ConnectorLink(
            provider="bigballsdata",
            competition_id=competition.id,
            season_id=season.id,
            external_league_id="ligue-1",
            external_season="2025",
        )
        db.add(link)
        db.commit()

        run = service.preview_fixtures(db, link)
        db.commit()
        item = _require(run.payload)["matches"][0]
        assert item["action"] == "conflict"
        assert item["match_id"] == match_id
        counts = service.apply_preview(db, run)
        db.commit()
        match = _require(db.get(Match, UUID(match_id)))
        assert match.home_score == 4
        assert match.away_score == 4
        assert counts.conflicts == 1


def test_fixture_window_keeps_results_and_excludes_far_fixtures(
    engine, seeded_db, monkeypatch
) -> None:
    _setup(engine)
    now = datetime.now(UTC)
    near = _raw_match("bbd-near", kickoff=now + timedelta(days=3))
    far = _raw_match("bbd-far", kickoff=now + timedelta(days=20))
    result = _raw_match(
        "bbd-old",
        status="finished",
        score={"home": 2, "away": 1},
        kickoff=now - timedelta(days=400),
    )
    monkeypatch.setattr(
        service, "client_for", lambda *_, **__: FakeBigBalls([near, far, result])
    )
    with Session(engine) as db:
        link = _require(db.scalar(select(ConnectorLink)))
        run = service.preview_fixtures(db, link)
        db.commit()

        payload = _require(run.payload)
        external_ids = {item["external_id"] for item in payload["matches"]}
        assert external_ids == {"bbd-near", "bbd-old"}
        assert run.summary["counts"]["received"] == 3
        assert run.summary["counts"]["created"] == 2
        warnings = run.summary["warnings"]
        assert any("10 prochains jours" in warning for warning in warnings)
        assert any("1 rencontre(s)" in warning for warning in warnings)

        counts = service.apply_preview(db, run)
        db.commit()
        assert counts.created == 2
        assert db.scalar(select(func.count()).select_from(Match)) == 2


def test_fixture_window_boundary_and_non_programmed_status() -> None:
    now = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
    entries = [
        {"status": "programme", "kickoff_at": now + timedelta(days=10)},
        {"status": "programme", "kickoff_at": now + timedelta(days=10, seconds=1)},
        {"status": "termine", "kickoff_at": now + timedelta(days=400)},
    ]

    kept, excluded, horizon = service._within_fixture_window(entries, now=now)

    assert horizon == now + timedelta(days=service.FIXTURE_WINDOW_DAYS)
    assert [item["status"] for item in kept] == ["programme", "termine"]
    assert excluded == 1


def test_odds_preview_and_apply_are_append_only(engine, seeded_db, monkeypatch) -> None:
    _setup_internal_match(engine)
    monkeypatch.setattr(service, "client_for", lambda *_, **__: FakeOdds([_event()]))
    with Session(engine) as db:
        link = _require(db.scalar(select(ConnectorLink)))
        run = service.preview_odds(db, link)
        db.commit()
        assert run.credits_used == 2
        assert run.summary["counts"]["created"] == 2
        assert db.scalar(select(func.count()).select_from(Market)) == 0

        counts = service.apply_preview(db, run)
        db.commit()
        assert counts.updated == 2
        assert db.scalar(select(func.count()).select_from(Market)) == 2
        assert db.scalar(select(func.count()).select_from(Selection)) == 5
        assert db.scalar(select(func.count()).select_from(OddsSnapshot)) == 5

        replay = service.preview_odds(db, link)
        db.commit()
        service.apply_preview(db, replay)
        db.commit()
        assert db.scalar(select(func.count()).select_from(OddsSnapshot)) == 5
        snapshots = db.scalars(select(OddsSnapshot)).all()
        assert {snap.source for snap in snapshots} == {"the_odds_api"}
        assert {snap.bookmaker for snap in snapshots} == {"1xBet"}


def test_missing_bookmaker_imports_nothing(engine, seeded_db, monkeypatch) -> None:
    _setup_internal_match(engine)
    monkeypatch.setattr(
        service, "client_for", lambda *_, **__: FakeOdds([_event(bookmaker="unibet")])
    )
    with Session(engine) as db:
        link = _require(db.scalar(select(ConnectorLink)))
        run = service.preview_odds(db, link)
        db.commit()
        assert run.summary["counts"]["created"] == 0
        assert any("1xBet" in warning for warning in run.summary["warnings"])
        service.apply_preview(db, run)
        db.commit()
        assert db.scalar(select(func.count()).select_from(Market)) == 0


def test_extended_markets_are_limited_and_flagged(engine, seeded_db, monkeypatch) -> None:
    match_id, _, _ = _setup_internal_match(engine)
    with Session(engine) as db:
        from app.connectors.import_common import link_ref

        link_ref(
            db,
            "the_odds_api",
            RefEntity.MATCH,
            _require(db.get(Match, UUID(match_id))).id,
            "evt-1",
        )
        db.commit()

    extended = {
        "evt-1": {
            "id": "evt-1",
            "commence_time": KICKOFF.isoformat().replace("+00:00", "Z"),
            "home_team": "Paris Saint-Germain",
            "away_team": "RC Lens",
            "bookmakers": [
                {
                    "key": "onexbet",
                    "title": "1xBet",
                    "last_update": "2026-11-10T09:30:00Z",
                    "markets": [
                        {
                            "key": "double_chance",
                            "outcomes": [
                                {"name": "1X", "price": 1.2},
                                {"name": "12", "price": 1.28},
                                {"name": "X2", "price": 2.4},
                            ],
                        },
                        {
                            "key": "btts",
                            "outcomes": [
                                {"name": "Yes", "price": 1.75},
                                {"name": "No", "price": 2.05},
                            ],
                        },
                    ],
                }
            ],
        }
    }
    monkeypatch.setattr(service, "client_for", lambda *_, **__: FakeOdds([], extended))
    with Session(engine) as db:
        link = _require(db.scalar(select(ConnectorLink)))
        run = service.preview_extended_odds(
            db, link, [_require(db.get(Match, UUID(match_id))).id]
        )
        db.commit()
        assert run.credits_used == 2
        assert run.summary["counts"]["created"] == 2
        service.apply_preview(db, run)
        db.commit()
        codes = set(db.scalars(select(Market.template_code)).all())
        assert codes == {"football.double_chance", "football.btts"}


def test_stats_batch_and_manual_conflict(engine, seeded_db, monkeypatch) -> None:
    match_id, _, _ = _setup_internal_match(engine)
    with Session(engine) as db:
        from app.connectors.import_common import link_ref

        match = _require(db.get(Match, UUID(match_id)))
        match.status = MatchStatus.TERMINE
        match.home_score = 2
        match.away_score = 1
        link_ref(db, "bigballsdata", RefEntity.MATCH, match.id, "bbd-1")
        link_ref(db, "bigballsdata", RefEntity.TEAM, match.home_team_id, "bbd-h")
        link_ref(db, "bigballsdata", RefEntity.TEAM, match.away_team_id, "bbd-a")
        competition = _require(
            db.scalar(select(Competition).where(Competition.name == COMPETITION))
        )
        season = _require(
            db.scalar(select(Season).where(Season.competition_id == competition.id))
        )
        db.add(
            ConnectorLink(
                provider="bigballsdata",
                competition_id=competition.id,
                season_id=season.id,
                external_league_id="ligue-1",
                external_season="2025",
            )
        )
        db.commit()

    stats = {
        "bbd-1": {
            "home": {
                "team_id": "bbd-h",
                "total_shots": 12,
                "shots_on_target": 5,
                "ball_possession": 58.0,
                "corner_kicks": 6,
                "yellow_cards": 1,
            },
            "away": {
                "team_id": "bbd-a",
                "total_shots": 8,
                "shots_on_target": 3,
                "ball_possession": 42.0,
                "corner_kicks": 4,
                "yellow_cards": 3,
            },
        }
    }
    monkeypatch.setattr(service, "client_for", lambda *_, **__: FakeBigBalls([], stats))
    with Session(engine) as db:
        link = _require(
            db.scalar(select(ConnectorLink).where(ConnectorLink.provider == "bigballsdata"))
        )
        result = service.apply_stats_batch(db, link, [UUID(match_id)])
        assert result["created"] == 1
        rows = db.scalars(select(TeamMatchStats)).all()
        assert len(rows) == 2
        assert {row.data_source for row in rows} == {"bigballsdata"}
        home = next(row for row in rows if row.is_home)
        assert home.goals_for == 2
        assert home.goals_against == 1

        again = service.apply_stats_batch(db, link, [UUID(match_id)])
        assert again["conflicts"] == 1
        assert db.scalar(select(func.count()).select_from(TeamMatchStats)) == 2


def test_provider_refs_are_unique(engine, seeded_db) -> None:
    _setup_internal_match(engine)
    with Session(engine) as db:
        match = _require(db.scalar(select(Match)))
        from app.connectors.import_common import link_ref

        link_ref(db, "the_odds_api", RefEntity.MATCH, match.id, "evt-x")
        db.commit()
        link_ref(db, "the_odds_api", RefEntity.MATCH, match.id, "evt-x")
        db.commit()
        count = db.scalar(
            select(func.count())
            .select_from(ProviderRef)
            .where(ProviderRef.external_id == "evt-x")
        )
        assert count == 1
        run_count = db.scalar(select(func.count()).select_from(SyncRun))
        assert run_count == 0
