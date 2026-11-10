"""Tests des mappings purs et de la normalisation des noms."""

from app.connectors.bigballsdata.mapping import map_match, map_statistics, parse_datetime
from app.connectors.matching import kickoff_close, normalize_name, same_team, similar_teams
from app.connectors.the_odds_api.mapping import map_event_odds, map_events, valid_price


def _event(markets: list[dict], *, bookmaker: str = "onexbet") -> dict:
    return {
        "id": "evt-1",
        "commence_time": "2026-11-15T16:00:00Z",
        "home_team": "Paris Saint-Germain",
        "away_team": "RC Lens",
        "bookmakers": [
            {
                "key": bookmaker,
                "title": "1xBet",
                "last_update": "2026-11-10T09:30:00Z",
                "markets": markets,
            }
        ],
    }


def test_h2h_mapping_uses_internal_codes() -> None:
    event = map_event_odds(
        _event(
            [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Paris Saint-Germain", "price": 1.55},
                        {"name": "Draw", "price": 4.2},
                        {"name": "RC Lens", "price": 6.1},
                    ],
                }
            ]
        )
    )
    assert event is not None
    assert event.bookmaker == "1xBet"
    assert event.markets[0].template_code == "football.resultat_1x2"
    assert event.markets[0].outcomes == {"1": 1.55, "X": 4.2, "2": 6.1}


def test_h2h_incomplete_is_ignored() -> None:
    event = map_event_odds(
        _event(
            [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Paris Saint-Germain", "price": 1.55},
                        {"name": "Draw", "price": 4.2},
                    ],
                }
            ]
        )
    )
    assert event is not None
    assert event.markets == []
    assert event.ignored == 1


def test_totals_require_both_sides_and_group_lines() -> None:
    event = map_event_odds(
        _event(
            [
                {
                    "key": "totals",
                    "outcomes": [
                        {"name": "Over", "point": 2.5, "price": 1.9},
                        {"name": "Under", "point": 2.5, "price": 1.92},
                        {"name": "Over", "point": 3.5, "price": 2.4},
                    ],
                }
            ]
        )
    )
    assert event is not None
    assert len(event.markets) == 1
    market = event.markets[0]
    assert market.template_code == "football.total_buts"
    assert market.line == 2.5
    assert market.outcomes == {"plus": 1.9, "moins": 1.92}
    assert event.ignored == 1


def test_double_chance_accepts_names_and_literals() -> None:
    named = map_event_odds(
        _event(
            [
                {
                    "key": "double_chance",
                    "outcomes": [
                        {"name": "Paris Saint-Germain or Draw", "price": 1.2},
                        {"name": "Paris Saint-Germain or RC Lens", "price": 1.28},
                        {"name": "Draw or RC Lens", "price": 2.4},
                    ],
                }
            ]
        )
    )
    assert named is not None
    assert named.markets[0].outcomes == {"1X": 1.2, "12": 1.28, "X2": 2.4}

    literal = map_event_odds(
        _event(
            [
                {
                    "key": "double_chance",
                    "outcomes": [
                        {"name": "1X", "price": 1.2},
                        {"name": "12", "price": 1.28},
                        {"name": "X2", "price": 2.4},
                    ],
                }
            ]
        )
    )
    assert literal is not None
    assert literal.markets[0].outcomes == {"1X": 1.2, "12": 1.28, "X2": 2.4}


def test_btts_and_unknown_markets() -> None:
    event = map_event_odds(
        _event(
            [
                {
                    "key": "btts",
                    "outcomes": [
                        {"name": "Yes", "price": 1.75},
                        {"name": "No", "price": 2.05},
                    ],
                },
                {
                    "key": "spreads",
                    "outcomes": [{"name": "Paris Saint-Germain", "price": 1.9}],
                },
            ]
        )
    )
    assert event is not None
    assert len(event.markets) == 1
    assert event.markets[0].template_code == "football.btts"
    assert event.markets[0].outcomes == {"oui": 1.75, "non": 2.05}


def test_bookmaker_absent_returns_none() -> None:
    assert map_event_odds(_event([], bookmaker="unibet")) is None
    assert map_events([_event([], bookmaker="unibet")]) == []


def test_invalid_prices_rejected() -> None:
    assert valid_price(1.01) is None
    assert valid_price(1000) is None
    assert valid_price("2.0") is None
    assert valid_price(2.123456789) == 2.123457


def test_event_without_bookmakers_or_teams_is_ignored() -> None:
    assert map_event_odds({"id": "x"}) is None
    assert map_event_odds({**_event([]), "home_team": ""}) is None


def test_bigballsdata_match_mapping() -> None:
    match = map_match(
        {
            "id": "m-1",
            "kickoff_utc": "2026-11-15T16:00:00Z",
            "status": "suspended",
            "home": {"id": "t-1", "name": "Paris Saint-Germain", "short_name": "PSG"},
            "away": {"id": "t-2", "name": "RC Lens"},
            "score": {"home": 1, "away": 1},
        },
        competition_external_id="ligue-1",
        season_label="2025",
    )
    assert match.status == "en_cours"
    assert match.raw_status == "suspended"
    assert match.home.short_name == "PSG"
    assert match.home_score == match.away_score == 1
    assert parse_datetime(match.kickoff_at).tzinfo is not None


def test_bigballsdata_unknown_status_defaults_and_is_reported() -> None:
    match = map_match(
        {
            "id": "m-2",
            "kickoff_utc": "2026-11-15T16:00:00Z",
            "status": "mystery",
            "home": {"id": "t-1", "name": "A"},
            "away": {"id": "t-2", "name": "B"},
            "score": None,
        },
        competition_external_id="ligue-1",
        season_label="2025",
    )
    assert match.status == "programme"
    assert match.home_score is None


def test_bigballsdata_statistics_mapping_without_invention() -> None:
    lines = map_statistics(
        {
            "home": {
                "team_id": "t-1",
                "total_shots": 12,
                "shots_on_target": 5,
                "ball_possession": 58.5,
                "corner_kicks": 6,
                "yellow_cards": 2,
                "red_cards": None,
            },
            "away": None,
        },
        match_external_id="m-1",
        home_id="t-1",
        away_id="t-2",
    )
    assert len(lines) == 1
    assert lines[0].possession == 58.5
    assert lines[0].expected_goals is None
    assert lines[0].red_cards is None


def test_football_data_mapping() -> None:
    from app.connectors.football_data.mapping import map_match as fd_map

    match = fd_map(
        {
            "id": 42,
            "utcDate": "2026-11-15T16:00:00Z",
            "status": "FINISHED",
            "competition": {"code": "FL1", "name": "Ligue 1"},
            "season": {"startDate": "2026-08-01"},
            "homeTeam": {"id": 1, "name": "Paris Saint-Germain", "shortName": "PSG"},
            "awayTeam": {"id": 2, "name": "RC Lens", "tla": "RCL"},
            "score": {
                "fullTime": {"home": 2, "away": 1},
                "halfTime": {"home": 1, "away": 0},
            },
        }
    )
    assert match.external_id == "42"
    assert match.competition_external_id == "FL1"
    assert match.season_label == "2026"
    assert match.status == "termine"
    assert match.home_score == 2
    assert match.half_time_away_score == 0


def test_name_normalization_and_suggestions() -> None:
    assert normalize_name("Paris Saint-Germain FC") == "paris saint germain"
    assert normalize_name("Équipe Alpha") == "equipe alpha"
    assert same_team("Paris SG", "PSG", "Paris Saint-Germain", "PSG")
    assert not same_team("Lens", None, "Lille", None)
    suggestions = similar_teams("Paris Saint Germain", [("t1", "Paris Saint-Germain", "PSG")])
    assert suggestions and suggestions[0][0] == "t1"


def test_kickoff_tolerance() -> None:
    from datetime import UTC, datetime

    left = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)
    right = datetime(2026, 11, 15, 16, 25, tzinfo=UTC)
    assert kickoff_close(left, right)
    assert not kickoff_close(left, datetime(2026, 11, 15, 17, 30, tzinfo=UTC))
