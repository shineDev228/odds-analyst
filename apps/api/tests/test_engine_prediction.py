"""Tests du moteur de prédiction football (fonctions pures)."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from engine.markets.football import derive_probabilities
from engine.models.poisson import score_matrices, score_matrix
from engine.prediction import MODEL_VERSION, predict_football, predict_point_football
from engine.ratings import (
    HistoricalMatch,
    InsufficientDataError,
    RatingConfig,
    estimate_ratings,
)
from engine.uncertainty import simulate_markets

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
    assert MODEL_VERSION == "football-poisson-v2"
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


def _history_with_statistics(
    *,
    team: str = "A",
    opponent: str = "B",
    goals: int = 1,
    count: int = 10,
    xg: float | None = None,
    shots_on_target: int | None = None,
) -> list[HistoricalMatch]:
    """Historique où l'équipe `team` affiche la même statistique à chaque match."""
    matches: list[HistoricalMatch] = []
    for index in range(count):
        days_ago = index * 7 + 1
        home_expected = xg
        away_expected = float(goals) if xg is not None else None
        home_shots = shots_on_target
        away_shots = goals if shots_on_target is not None else None
        if index % 2 == 0:
            matches.append(
                HistoricalMatch(
                    home_team_id=team,
                    away_team_id=opponent,
                    home_goals=goals,
                    away_goals=goals,
                    played_at=AS_OF - timedelta(days=days_ago),
                    home_expected_goals=home_expected,
                    away_expected_goals=away_expected,
                    home_shots_on_target=home_shots,
                    away_shots_on_target=away_shots,
                )
            )
        else:
            matches.append(
                HistoricalMatch(
                    home_team_id=opponent,
                    away_team_id=team,
                    home_goals=goals,
                    away_goals=goals,
                    played_at=AS_OF - timedelta(days=days_ago),
                    home_expected_goals=away_expected,
                    away_expected_goals=home_expected,
                    home_shots_on_target=away_shots,
                    away_shots_on_target=home_shots,
                )
            )
    return matches


def test_xg_improves_attack_when_goals_underperform() -> None:
    goals_only = estimate_ratings(
        _history(goals_a=1, goals_b=1, count=10),
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    with_xg = estimate_ratings(
        _history_with_statistics(xg=2.5, count=10),
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    assert with_xg.home.attack > goals_only.home.attack
    assert with_xg.home_lambda > goals_only.home_lambda
    assert with_xg.home.xg_matches == 10
    assert with_xg.home.xg_coverage == pytest.approx(1.0)


def test_shots_on_target_provide_proxy_when_xg_missing() -> None:
    goals_only = estimate_ratings(
        _history(goals_a=1, goals_b=1, count=10),
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    with_proxy = estimate_ratings(
        _history_with_statistics(shots_on_target=8, count=10),
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    assert with_proxy.home.attack > goals_only.home.attack
    assert with_proxy.home.proxy_matches == 10
    assert with_proxy.home.statistics_method == "proxy"
    assert with_proxy.home.xg_coverage == pytest.approx(1.0)


def test_proxy_is_capped_at_four_expected_goals() -> None:
    capped = estimate_ratings(
        _history_with_statistics(shots_on_target=14, count=10),
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    excessive = estimate_ratings(
        _history_with_statistics(shots_on_target=30, count=10),
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    assert capped.home.attack == pytest.approx(excessive.home.attack)
    assert capped.home_lambda == pytest.approx(excessive.home_lambda)


def test_missing_statistics_fall_back_exactly_to_goals() -> None:
    without = estimate_ratings(
        _history(goals_a=1, goals_b=1, count=10),
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    neutral_xg = estimate_ratings(
        _history_with_statistics(xg=None, count=10),
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    assert without.home.attack == pytest.approx(neutral_xg.home.attack)
    assert without.home_lambda == pytest.approx(neutral_xg.home_lambda)
    assert without.home.xg_coverage == 0.0
    assert without.home.statistics_method == "buts"
    assert without.home.goals_only_matches == 10


def test_xg_equal_to_goals_changes_nothing() -> None:
    without = estimate_ratings(
        _history(goals_a=1, goals_b=1, count=10),
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    identity = estimate_ratings(
        _history_with_statistics(xg=1.0, count=10),
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    assert without.home.attack == pytest.approx(identity.home.attack)
    assert without.home.defense == pytest.approx(identity.home.defense)
    assert without.home_lambda == pytest.approx(identity.home_lambda)
    assert identity.home.xg_matches == 10


def test_mixed_statistics_expose_coverage_and_method() -> None:
    matches: list[HistoricalMatch] = []
    for index in range(10):
        days_ago = index * 7 + 1
        if index < 5:
            home_expected: float | None = 1.5
            away_expected: float | None = 1.0
            home_shots: int | None = None
            away_shots: int | None = None
        else:
            home_expected = None
            away_expected = None
            home_shots = 5
            away_shots = 3
        matches.append(
            HistoricalMatch(
                home_team_id="A",
                away_team_id="B",
                home_goals=1,
                away_goals=1,
                played_at=AS_OF - timedelta(days=days_ago),
                home_expected_goals=home_expected,
                away_expected_goals=away_expected,
                home_shots_on_target=home_shots,
                away_shots_on_target=away_shots,
            )
        )

    ratings = estimate_ratings(
        matches,
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    assert ratings.home.xg_matches == 5
    assert ratings.home.proxy_matches == 5
    assert ratings.home.statistics_method == "xg_et_proxy"
    assert 0.0 < ratings.home.xg_coverage <= 1.0


def test_point_prediction_skips_simulations_but_keeps_markets() -> None:
    point = predict_point_football(
        _history(count=10),
        league_matches=_history(count=10),
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    assert point.markets.home_win + point.markets.draw + point.markets.away_win == (
        pytest.approx(1.0)
    )
    assert point.ratings.dixon_coles_rho == pytest.approx(point.ratings.rho_estimate.value)
    assert point.quality.matches_home == 10


def test_estimated_rho_is_bounded_and_deterministic() -> None:
    first = _prediction(_history(count=12))
    second = _prediction(_history(count=12))
    assert -0.20 <= first.ratings.dixon_coles_rho <= 0.15
    assert first.ratings.dixon_coles_rho == second.ratings.dixon_coles_rho


def test_batched_score_matrices_match_single_calls() -> None:
    """La version groupée doit reproduire exactement la matrice unitaire."""
    home = np.array([0.0, 0.6, 1.6, 3.2, 12.0])
    away = np.array([-1.0, 1.1, 0.9, 2.4, 0.2])
    batch = score_matrices(home, away, max_goals=7, rho=-0.05)
    assert batch.shape == (5, 8, 8)
    for index in range(home.size):
        expected = score_matrix(float(home[index]), float(away[index]), max_goals=7, rho=-0.05)
        assert np.allclose(batch[index], expected.probabilities, rtol=1e-12, atol=1e-15)
        assert batch[index].sum() == pytest.approx(1.0)


def test_simulated_intervals_are_reproducible() -> None:
    ratings = estimate_ratings(
        _history(count=10),
        home_team_id="A",
        away_team_id="B",
        as_of=AS_OF,
        config=CONFIG,
    )
    first = simulate_markets(ratings, CONFIG, simulations=200)
    second = simulate_markets(ratings, CONFIG, simulations=200)
    assert first == second
    for interval in (first.home_win, first.draw, first.away_win, first.btts_yes):
        assert 0.0 <= interval.low <= interval.median <= interval.high <= 1.0
    for total in first.totals:
        assert total.over.low <= total.over.median <= total.over.high
        assert total.under.low <= total.under.median <= total.under.high
