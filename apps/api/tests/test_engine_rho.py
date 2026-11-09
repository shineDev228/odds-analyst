"""Tests de l'estimation régularisée du paramètre Dixon-Coles `rho`."""

import pytest
from engine.models.rho import estimate_rho

LAMBDA_HOME = 1.4
LAMBDA_AWAY = 1.1


def _estimate(
    observations,
    *,
    prior: float = -0.05,
    prior_matches: float = 30.0,
    minimum: float = -0.20,
    maximum: float = 0.15,
    step: float = 0.005,
    max_goals: int = 10,
):
    return estimate_rho(
        observations,
        lambda_home=LAMBDA_HOME,
        lambda_away=LAMBDA_AWAY,
        prior=prior,
        prior_matches=prior_matches,
        minimum=minimum,
        maximum=maximum,
        step=step,
        max_goals=max_goals,
    )


def test_no_observation_returns_the_prior() -> None:
    result = _estimate([])
    assert result.value == pytest.approx(-0.05)
    assert result.observations == 0
    assert result.effective_matches == 0.0


def test_estimate_is_bounded_and_deterministic() -> None:
    observations = [(0, 0, 1.0), (1, 1, 1.0), (2, 1, 1.0)]
    first = _estimate(observations)
    second = _estimate(observations)
    assert -0.20 <= first.value <= 0.15
    assert first == second


def test_low_score_draws_push_rho_down() -> None:
    draws = [(1, 1, 1.0)] * 120
    wins = [(1, 0, 1.0)] * 120
    draws_estimate = _estimate(draws, prior_matches=0.0)
    wins_estimate = _estimate(wins, prior_matches=0.0)
    assert draws_estimate.raw < wins_estimate.raw
    assert draws_estimate.value < wins_estimate.value


def test_small_sample_stays_close_to_the_prior() -> None:
    observations = [(1, 0, 1.0)]
    result = _estimate(observations)
    assert abs(result.value - (-0.05)) < 0.02
    assert result.effective_matches == pytest.approx(1.0)


def test_shrinkage_decreases_with_sample_size() -> None:
    small = _estimate([(1, 1, 1.0)] * 2)
    large = _estimate([(1, 1, 1.0)] * 200)
    assert abs(large.value - (-0.05)) > abs(small.value - (-0.05))


def test_effective_matches_account_for_weights() -> None:
    observations = [(1, 0, 1.0), (1, 0, 1.0), (1, 0, 1.0), (1, 0, 1.0)]
    result = _estimate(observations)
    assert result.effective_matches == pytest.approx(4.0)
    assert result.observations == 4


def test_negative_weights_are_ignored() -> None:
    result = _estimate([(1, 0, -1.0), (0, 0, 0.0)])
    assert result.observations == 0
    assert result.value == pytest.approx(-0.05)


def test_invalid_parameters_are_rejected() -> None:
    with pytest.raises(ValueError):
        _estimate([(1, 0, 1.0)], minimum=0.15, maximum=-0.20)
    with pytest.raises(ValueError):
        _estimate([(1, 0, 1.0)], step=0.0)
    with pytest.raises(ValueError):
        _estimate([(1, 0, 1.0)], prior_matches=-1.0)
    with pytest.raises(ValueError):
        _estimate([(1, 0, 1.0)], prior=0.5)
