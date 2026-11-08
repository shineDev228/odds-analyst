"""Tests du générateur de combinaisons (moteur pur)."""

from datetime import UTC, datetime

import pytest
from engine.combos.generator import (
    CombinationCandidate,
    generate_combinations,
)

KICKOFF = datetime(2026, 12, 15, 20, 0, tzinfo=UTC)


def _candidate(
    match_id: str,
    key: str,
    odds: float,
    probability: float,
    *,
    low: float | None = None,
    high: float | None = None,
) -> CombinationCandidate:
    return CombinationCandidate(
        key=key,
        match_id=match_id,
        match_label=f"Rencontre {match_id}",
        competition_name="Ligue Test",
        kickoff_at=KICKOFF,
        market_name="Résultat",
        selection_label=key,
        decimal_odds=odds,
        probability=probability,
        low=probability if low is None else low,
        high=probability if high is None else high,
    )


def _groups() -> list[list[CombinationCandidate]]:
    return [
        [
            _candidate("m1", "1", 1.8, 0.55, low=0.45, high=0.65),
            _candidate("m1", "X", 3.4, 0.25, low=0.18, high=0.32),
        ],
        [
            _candidate("m2", "1", 1.7, 0.60, low=0.50, high=0.70),
            _candidate("m2", "2", 4.2, 0.20, low=0.12, high=0.28),
        ],
        [
            _candidate("m3", "plus", 1.9, 0.52, low=0.40, high=0.64),
            _candidate("m3", "moins", 1.9, 0.48, low=0.36, high=0.60),
        ],
    ]


def test_generates_exact_count_and_one_selection_per_match() -> None:
    result = generate_combinations(
        _groups(),
        selections_count=2,
        min_odds=2.5,
        max_odds=10.0,
    )
    assert result.combinations
    for combination in result.combinations:
        assert len(combination.selections) == 2
        assert len({item.match_id for item in combination.selections}) == 2
        assert 2.5 <= combination.total_odds <= 10.0
        expected_probability = 1.0
        for selection in combination.selections:
            expected_probability *= selection.probability
        assert combination.probability == pytest.approx(expected_probability)
        assert combination.low <= combination.probability <= combination.high
        assert combination.expected_value == pytest.approx(
            combination.probability * combination.total_odds - 1.0
        )


def test_respects_odds_bounds() -> None:
    result = generate_combinations(
        _groups(),
        selections_count=2,
        min_odds=3.0,
        max_odds=4.0,
    )
    assert result.combinations
    assert all(3.0 <= item.total_odds <= 4.0 for item in result.combinations)


def test_results_are_sorted_by_expected_value() -> None:
    result = generate_combinations(
        _groups(),
        selections_count=2,
        min_odds=2.0,
        max_odds=20.0,
        limit=10,
    )
    values = [item.expected_value for item in result.combinations]
    assert values == sorted(values, reverse=True)


def test_returns_empty_without_enough_matches() -> None:
    result = generate_combinations(
        _groups()[:1],
        selections_count=2,
        min_odds=2.0,
        max_odds=10.0,
    )
    assert result.combinations == ()
    assert result.truncated is False


def test_returns_empty_when_range_is_impossible() -> None:
    result = generate_combinations(
        _groups(),
        selections_count=3,
        min_odds=100.0,
        max_odds=200.0,
    )
    assert result.combinations == ()


def test_search_is_deterministic() -> None:
    first = generate_combinations(_groups(), selections_count=2, min_odds=2.0, max_odds=20.0)
    second = generate_combinations(_groups(), selections_count=2, min_odds=2.0, max_odds=20.0)
    assert first.combinations == second.combinations
    assert first.explored_nodes == second.explored_nodes


def test_search_reports_truncation() -> None:
    groups = [
        [
            _candidate(f"m{index}", "1", 1.2 + index * 0.01, 0.70),
            _candidate(f"m{index}", "2", 2.0 + index * 0.01, 0.30),
        ]
        for index in range(12)
    ]
    result = generate_combinations(
        groups,
        selections_count=8,
        min_odds=2.0,
        max_odds=100.0,
        max_nodes=10,
    )
    assert result.truncated is True


def test_rejects_invalid_parameters() -> None:
    with pytest.raises(ValueError):
        generate_combinations(_groups(), selections_count=1, min_odds=2.0, max_odds=10.0)
    with pytest.raises(ValueError):
        generate_combinations(_groups(), selections_count=2, min_odds=1.0, max_odds=10.0)
    with pytest.raises(ValueError):
        generate_combinations(_groups(), selections_count=2, min_odds=10.0, max_odds=5.0)


def test_rejects_group_mixing_two_matches() -> None:
    groups = [
        [
            _candidate("m1", "1", 1.8, 0.55),
            _candidate("m2", "1", 1.9, 0.50),
        ]
    ]
    with pytest.raises(ValueError):
        generate_combinations(groups, selections_count=2, min_odds=2.0, max_odds=10.0)
