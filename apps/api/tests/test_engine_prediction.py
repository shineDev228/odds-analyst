"""Tests du moteur de prédiction football (fonctions pures)."""

from datetime import UTC, datetime, timedelta

import pytest
from engine.markets.football import derive_probabilities
from engine.models.poisson import score_matrix
from engine.prediction import MODEL_VERSION, predict_football
from engine.ratings import (
    HistoricalMatch,
    InsufficientDataError,
    RatingConfig,
    estimate_ratings,
)

AS_OF = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)
CONFIG = RatingConfig(simulations=250, totals_lines=(2.5,), max_goals=10)


def _match(
    home: str, away: str, home_goals: int, away_goals: int, days_ago: int
) -> HistoricalMatch:
    return HistoricalMatch(
        home_team_id=home,
        away_team_id=away,
        home_goals=home_goals,
        away_goals=away_goals,
        played_at=AS_OF - timedelta(days=days_ago),
    )


def _history(
    team_a: str = "A",
    team_b: str = "B",
    goals_a: int = 2,
    goals_b: int = 1,
    count: int = 10,
) -> list[HistoricalMatch]:
    matches: list[HistoricalMatch] = []
    for index in range(count):
        days_ago = index * 7 + 1
        if index % 2 == 0:
            matches.append(_match(team_a, team_b, goals_a, goals_b, days_ago))
        else:
            matches.append(_match(team_b, team_a, goals_b, goals_a, days_ago))
    return matches


def _prediction(history: list[HistoricalMatch], config: RatingConfig = CONFIG):
    return predict_football(
        history,
        league_matches=history,
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=config,
    )


def test_score_matrix_sums_to_one() -> None:
    matrix = score_matrix(1.6, 1.1, max_goals=8, rho=-0.05)
    assert matrix.probabilities.sum() == pytest.approx(1.0)
    assert (matrix.probabilities >= 0).all()


def test_derived_outcomes_sum_to_one() -> None:
    matrix = score_matrix(1.4, 1.2, max_goals=8, rho=0.0)
    markets = derive_probabilities(matrix.probabilities, totals_lines=(2.5,))
    assert markets.home_win + markets.draw + markets.away_win == pytest.approx(1.0)
    assert markets.home_or_draw == pytest.approx(markets.home_win + markets.draw)
    assert markets.home_or_away == pytest.approx(markets.home_win + markets.away_win)
    assert markets.draw_or_away == pytest.approx(markets.draw + markets.away_win)


def test_totals_are_complementary_for_half_line() -> None:
    matrix = score_matrix(1.5, 1.3, max_goals=8, rho=0.0)
    markets = derive_probabilities(matrix.probabilities, totals_lines=(2.5,))
    total = markets.totals[0]
    assert total.over + total.under == pytest.approx(1.0)
    assert total.push == pytest.approx(0.0)


def test_integer_total_includes_push() -> None:
    matrix = score_matrix(1.5, 1.3, max_goals=8, rho=0.0)
    markets = derive_probabilities(matrix.probabilities, totals_lines=(2.0,))
    total = markets.totals[0]
    assert total.push > 0
    assert total.over + total.under + total.push == pytest.approx(1.0)


def test_btts_is_complementary() -> None:
    matrix = score_matrix(1.6, 1.1, max_goals=8)
    markets = derive_probabilities(matrix.probabilities, totals_lines=(2.5,))
    assert markets.btts_yes + markets.btts_no == pytest.approx(1.0)
    assert 0.0 <= markets.btts_yes <= 1.0


def test_dixon_coles_boosts_low_scores() -> None:
    without = score_matrix(1.2, 0.9, max_goals=8, rho=0.0).probabilities
    with_correction = score_matrix(1.2, 0.9, max_goals=8, rho=-0.08).probabilities
    assert with_correction[0, 0] > without[0, 0]
    assert with_correction[1, 1] > without[1, 1]


def test_stronger_attack_increases_expected_goals() -> None:
    weak = estimate_ratings(
        _history(goals_a=1, goals_b=1),
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    strong = estimate_ratings(
        _history(goals_a=3, goals_b=1),
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    assert strong.home_lambda > weak.home_lambda
    assert strong.home.attack > weak.home.attack


def test_recency_weighting_favours_recent_form() -> None:
    recent_good = []
    recent_bad = []
    for index in range(10):
        days_ago = index * 7 + 1
        if index % 2 == 0:
            recent_good.append(_match("A", "B", 3 if index < 5 else 0, 1, days_ago))
            recent_bad.append(_match("A", "B", 0 if index < 5 else 3, 1, days_ago))
        else:
            recent_good.append(_match("B", "A", 1, 3 if index < 5 else 0, days_ago))
            recent_bad.append(_match("B", "A", 1, 0 if index < 5 else 3, days_ago))

    good = estimate_ratings(
        recent_good, home_team_id="A", away_team_id="B", as_of=AS_OF, config=CONFIG
    )
    bad = estimate_ratings(
        recent_bad, home_team_id="A", away_team_id="B", as_of=AS_OF, config=CONFIG
    )
    assert good.home.attack > bad.home.attack
    assert good.home_lambda > bad.home_lambda


def test_insufficient_history_raises() -> None:
    history = _history(count=2)
    with pytest.raises(InsufficientDataError) as error:
        estimate_ratings(
            history,
            home_team_id="A",
            away_team_id="B",
            as_of=AS_OF,
            config=CONFIG,
        )
    assert error.value.required == 3
    assert error.value.home_matches == 2
    assert error.value.away_matches == 2


def test_prediction_probabilities_and_intervals_are_ordered() -> None:
    prediction = _prediction(_history(count=10))
    assert prediction.config is CONFIG
    assert MODEL_VERSION == "football-poisson-v1"
    assert prediction.expected_goals_home > 0
    assert prediction.expected_goals_away > 0
    assert sum(item.probability for item in prediction.resultat) == pytest.approx(1.0)
    for item in (*prediction.resultat, *prediction.double_chance, *prediction.btts):
        assert 0.0 <= item.low <= item.probability <= item.high <= 1.0
    for total in prediction.totaux:
        assert total.over.low <= total.over.probability <= total.over.high
        assert total.under.low <= total.under.probability <= total.under.high
    assert prediction.scores_exacts
    assert all(score.probability >= 0 for score in prediction.scores_exacts)


def test_prediction_is_deterministic() -> None:
    history = _history(count=8)
    first = _prediction(history)
    second = _prediction(history)
    assert first.expected_goals_home == second.expected_goals_home
    assert first.resultat == second.resultat
    assert first.intervals.home_win == second.intervals.home_win


def test_more_history_narrows_the_interval() -> None:
    small = _prediction(_history(count=6), RatingConfig(simulations=300))
    large = _prediction(_history(count=30), RatingConfig(simulations=300))
    small_width = small.resultat[0].high - small.resultat[0].low
    large_width = large.resultat[0].high - large.resultat[0].low
    assert large_width < small_width


def test_quality_level_depends_on_effective_sample() -> None:
    small = _prediction(_history(count=6))
    large = _prediction(_history(count=30))
    assert small.quality.level in {"tres_faible", "faible"}
    assert large.quality.level in {"moyenne", "correcte", "bonne"}
    assert large.quality.effective_matches > small.quality.effective_matches
