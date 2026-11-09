"""Tests des métriques pures de calibration."""

from datetime import UTC, datetime, timedelta
from math import log

import pytest
from engine.calibration import CalibrationObservation, evaluate_calibration

START = datetime(2026, 9, 1, 18, 0, tzinfo=UTC)


def _observation(
    index: int,
    home_win: float,
    draw: float,
    away_win: float,
    home_goals: int,
    away_goals: int,
    *,
    xg_coverage: float = 0.0,
) -> CalibrationObservation:
    return CalibrationObservation(
        match_id=f"match-{index}",
        kickoff_at=START + timedelta(days=index),
        home_win=home_win,
        draw=draw,
        away_win=away_win,
        home_goals=home_goals,
        away_goals=away_goals,
        xg_coverage=xg_coverage,
    )


def test_empty_sample_returns_no_metrics() -> None:
    report = evaluate_calibration([])
    assert report.matches == 0
    assert report.brier is None
    assert report.log_loss is None
    assert report.accuracy is None
    assert report.brier_skill is None
    assert report.ece is None
    assert report.mean_xg_coverage is None
    assert report.bins == ()


def test_perfect_predictions_have_zero_loss() -> None:
    observations = [
        _observation(0, 1.0, 0.0, 0.0, 2, 0),
        _observation(1, 0.0, 1.0, 0.0, 1, 1),
        _observation(2, 0.0, 0.0, 1.0, 0, 3),
    ]
    report = evaluate_calibration(observations)
    assert report.brier == pytest.approx(0.0)
    assert report.log_loss == pytest.approx(0.0)
    assert report.accuracy == pytest.approx(1.0)
    assert report.ece == pytest.approx(0.0)
    assert report.baseline_brier == pytest.approx(2.0 / 3.0)
    assert report.brier_skill == pytest.approx(1.0)


def test_constant_base_rate_prediction_has_no_skill() -> None:
    observations = [
        _observation(0, 0.5, 0.0, 0.5, 2, 0),
        _observation(1, 0.5, 0.0, 0.5, 0, 2),
        _observation(2, 0.5, 0.0, 0.5, 3, 1),
        _observation(3, 0.5, 0.0, 0.5, 1, 3),
    ]
    report = evaluate_calibration(observations)
    assert report.brier == pytest.approx(report.baseline_brier or 0.0)
    assert report.brier_skill == pytest.approx(0.0)


def test_skill_is_positive_for_better_than_baseline() -> None:
    observations = [
        _observation(0, 0.8, 0.1, 0.1, 2, 0),
        _observation(1, 0.8, 0.1, 0.1, 1, 0),
        _observation(2, 0.2, 0.2, 0.6, 0, 2),
        _observation(3, 0.2, 0.2, 0.6, 0, 1),
    ]
    report = evaluate_calibration(observations)
    assert report.brier_skill is not None
    assert report.brier_skill > 0.0


def test_log_loss_is_bounded_for_impossible_outcome() -> None:
    observation = _observation(0, 1.0, 0.0, 0.0, 0, 1)
    report = evaluate_calibration([observation])
    assert report.log_loss == pytest.approx(-log(1e-6))


def test_bins_cover_every_probability_once() -> None:
    observations = [
        _observation(0, 0.6, 0.3, 0.1, 2, 1),
        _observation(1, 0.2, 0.5, 0.3, 1, 1),
    ]
    report = evaluate_calibration(observations, bins=10)
    assert len(report.bins) == 10
    assert sum(item.count for item in report.bins) == 6
    assert report.home_wins + report.draws + report.away_wins == 2
    for item in report.bins:
        assert 0.0 <= item.observed <= 1.0
        assert 0.0 <= item.mean_predicted <= 1.0
        assert 0.0 <= item.wilson_low <= item.wilson_high <= 1.0


def test_empty_bins_are_reported_with_zeros() -> None:
    report = evaluate_calibration([_observation(0, 1.0, 0.0, 0.0, 1, 0)])
    empty = [item for item in report.bins if item.count == 0]
    assert empty
    assert all(item.mean_predicted == 0.0 and item.observed == 0.0 for item in empty)


def test_wilson_interval_narrows_with_count() -> None:
    single = evaluate_calibration([_observation(0, 0.9, 0.05, 0.05, 1, 0)])
    many = evaluate_calibration([_observation(index, 0.9, 0.05, 0.05, 1, 0) for index in range(40)])
    single_bin = next(item for item in single.bins if item.count > 0)
    many_bin = next(item for item in many.bins if item.count > 0)
    assert many_bin.count > single_bin.count
    assert (many_bin.wilson_high - many_bin.wilson_low) < (
        single_bin.wilson_high - single_bin.wilson_low
    )


def test_ece_is_a_weighted_average() -> None:
    observations = [_observation(index, 0.7, 0.2, 0.1, 1, 0) for index in range(10)]
    report = evaluate_calibration(observations)
    assert report.ece is not None
    assert 0.0 <= report.ece <= 1.0
    assert report.ece > 0.0


def test_mean_xg_coverage() -> None:
    observations = [
        _observation(0, 0.5, 0.3, 0.2, 1, 0, xg_coverage=1.0),
        _observation(1, 0.5, 0.3, 0.2, 0, 1, xg_coverage=0.0),
    ]
    report = evaluate_calibration(observations)
    assert report.mean_xg_coverage == pytest.approx(0.5)


def test_calibration_is_deterministic() -> None:
    observations = [
        _observation(0, 0.5, 0.3, 0.2, 1, 0),
        _observation(1, 0.2, 0.3, 0.5, 0, 1),
    ]
    assert evaluate_calibration(observations) == evaluate_calibration(observations)


def test_invalid_observations_are_rejected() -> None:
    with pytest.raises(ValueError):
        _observation(0, 0.8, 0.3, 0.1, 1, 0)
    with pytest.raises(ValueError):
        _observation(0, -0.1, 0.6, 0.5, 1, 0)
    with pytest.raises(ValueError):
        _observation(0, 0.5, 0.5, 0.0, -1, 0)
    with pytest.raises(ValueError):
        _observation(0, 0.5, 0.5, 0.0, 1, 0, xg_coverage=1.5)
