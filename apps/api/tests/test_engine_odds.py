"""Tests du moteur pur de cotes."""

import pytest
from engine.odds import (
    InvalidOddsError,
    fair_odds,
    fair_probabilities,
    implied_probabilities,
    implied_probability,
    overround,
    overround_percent,
    validate_odds,
)


def test_implied_probability_of_evens() -> None:
    assert implied_probability(2.0) == pytest.approx(0.5)


def test_implied_probability_rejects_low_odds() -> None:
    for value in (1.0, 0.5, -2.0):
        with pytest.raises(InvalidOddsError):
            implied_probability(value)


def test_validate_odds_returns_float() -> None:
    assert isinstance(validate_odds(1.5), float)


def test_implied_probabilities_requires_values() -> None:
    with pytest.raises(InvalidOddsError):
        implied_probabilities([])


def test_overround_of_a_balanced_1x2() -> None:
    # 1 / 2.00 + 1 / 3.50 + 1 / 3.60 ≈ 1.0635
    odds = [2.0, 3.5, 3.6]
    assert overround(odds) == pytest.approx(0.063492, rel=1e-5)
    assert overround_percent(odds) == pytest.approx(6.3492, rel=1e-4)


def test_fair_probabilities_sum_to_one() -> None:
    probabilities = fair_probabilities([1.5, 4.0, 7.0])
    assert sum(probabilities) == pytest.approx(1.0)
    assert probabilities[0] > probabilities[1] > probabilities[2]


def test_fair_odds_are_higher_than_raw_odds_when_margin_positive() -> None:
    odds = [1.5, 4.0, 7.0]
    adjusted = fair_odds(odds)
    assert all(fair > raw for fair, raw in zip(adjusted, odds, strict=True))


def test_fair_odds_without_margin_are_unchanged() -> None:
    odds = [2.0, 2.0]
    assert fair_odds(odds) == pytest.approx(odds)


def test_fair_probabilities_reject_invalid_odds() -> None:
    with pytest.raises(InvalidOddsError):
        fair_probabilities([1.0, 2.0])
