"""Mesure pure de la calibration d'un modèle de probabilités.

Le rétro-test compare des probabilités estimées avant le coup d'envoi au
résultat réel. Le module ne connaît ni la base de données ni le moteur de
prédiction : il reçoit une liste d'observations et produit les indicateurs.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from math import log, sqrt

MIN_PROBABILITY = 1e-6
WILSON_Z = 1.959963984540054


@dataclass(frozen=True)
class CalibrationObservation:
    """Probabilités 1X2 estimées avant match et résultat réel."""

    match_id: str
    kickoff_at: datetime
    home_win: float
    draw: float
    away_win: float
    home_goals: int
    away_goals: int
    xg_coverage: float = 0.0

    def __post_init__(self) -> None:
        if self.home_goals < 0 or self.away_goals < 0:
            raise ValueError("Les scores de calibration doivent être positifs ou nuls.")
        probabilities = (self.home_win, self.draw, self.away_win)
        if any(not 0.0 <= value <= 1.0 for value in probabilities):
            raise ValueError("Chaque probabilité doit être comprise entre 0 et 1.")
        if abs(sum(probabilities) - 1.0) > 1e-6:
            raise ValueError("Les probabilités 1X2 doivent sommer à 1.")
        if not 0.0 <= self.xg_coverage <= 1.0:
            raise ValueError("La couverture xG doit être comprise entre 0 et 1.")

    @property
    def outcome(self) -> int:
        """Issue réelle : 0 = domicile, 1 = nul, 2 = extérieur."""
        if self.home_goals > self.away_goals:
            return 0
        if self.home_goals < self.away_goals:
            return 2
        return 1

    @property
    def probabilities(self) -> tuple[float, float, float]:
        return (self.home_win, self.draw, self.away_win)


@dataclass(frozen=True)
class CalibrationBin:
    """Tranche de probabilité et fréquence observée associée."""

    low: float
    high: float
    count: int
    mean_predicted: float
    observed: float
    wilson_low: float
    wilson_high: float


@dataclass(frozen=True)
class CalibrationReport:
    """Synthèse du rétro-test, avec `None` lorsque l'échantillon est vide."""

    matches: int
    home_wins: int
    draws: int
    away_wins: int
    brier: float | None
    log_loss: float | None
    accuracy: float | None
    baseline_brier: float | None
    baseline_log_loss: float | None
    brier_skill: float | None
    ece: float | None
    mean_xg_coverage: float | None
    bins: tuple[CalibrationBin, ...]


def _wilson_interval(successes: int, count: int) -> tuple[float, float]:
    if count <= 0:
        return 0.0, 0.0
    proportion = successes / count
    denominator = 1.0 + (WILSON_Z * WILSON_Z) / count
    center = (proportion + (WILSON_Z * WILSON_Z) / (2.0 * count)) / denominator
    margin = (
        WILSON_Z
        * sqrt(
            proportion * (1.0 - proportion) / count + (WILSON_Z * WILSON_Z) / (4.0 * count * count)
        )
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _brier(observation: CalibrationObservation) -> float:
    outcome = observation.outcome
    return sum(
        (probability - (1.0 if index == outcome else 0.0)) ** 2
        for index, probability in enumerate(observation.probabilities)
    )


def _log_loss(observation: CalibrationObservation) -> float:
    probability = observation.probabilities[observation.outcome]
    return -log(max(probability, MIN_PROBABILITY))


def _bin_index(probability: float, bins: int) -> int:
    if probability >= 1.0:
        return bins - 1
    return min(int(probability * bins), bins - 1)


def evaluate_calibration(
    observations: Sequence[CalibrationObservation],
    *,
    bins: int = 10,
) -> CalibrationReport:
    """Calcule les indicateurs de calibration d'un jeu d'observations."""
    if bins < 1:
        raise ValueError("Le nombre de tranches doit être positif.")
    if not observations:
        return CalibrationReport(
            matches=0,
            home_wins=0,
            draws=0,
            away_wins=0,
            brier=None,
            log_loss=None,
            accuracy=None,
            baseline_brier=None,
            baseline_log_loss=None,
            brier_skill=None,
            ece=None,
            mean_xg_coverage=None,
            bins=(),
        )

    matches = len(observations)
    home_wins = sum(1 for item in observations if item.outcome == 0)
    draws = sum(1 for item in observations if item.outcome == 1)
    away_wins = sum(1 for item in observations if item.outcome == 2)
    base_rates = (home_wins / matches, draws / matches, away_wins / matches)

    brier = sum(_brier(item) for item in observations) / matches
    log_loss = sum(_log_loss(item) for item in observations) / matches
    accuracy = (
        sum(
            1.0
            for item in observations
            if max(range(3), key=lambda index: item.probabilities[index]) == item.outcome
        )
        / matches
    )

    baseline_brier = (
        sum(
            sum(
                (base_rates[index] - (1.0 if index == item.outcome else 0.0)) ** 2
                for index in range(3)
            )
            for item in observations
        )
        / matches
    )
    baseline_log_loss = (
        sum(-log(max(base_rates[item.outcome], MIN_PROBABILITY)) for item in observations) / matches
    )

    brier_skill = None
    if baseline_brier > 0:
        brier_skill = 1.0 - brier / baseline_brier

    counts = [0] * bins
    predicted_sum = [0.0] * bins
    for item in observations:
        for probability in item.probabilities:
            position = _bin_index(probability, bins)
            counts[position] += 1
            predicted_sum[position] += probability

    successes = [0] * bins
    for item in observations:
        position = _bin_index(item.probabilities[item.outcome], bins)
        successes[position] += 1

    total_probabilities = sum(counts)
    calibration_bins: list[CalibrationBin] = []
    ece = 0.0
    for position in range(bins):
        count = counts[position]
        low = position / bins
        high = (position + 1) / bins
        if count == 0:
            calibration_bins.append(
                CalibrationBin(
                    low=low,
                    high=high,
                    count=0,
                    mean_predicted=0.0,
                    observed=0.0,
                    wilson_low=0.0,
                    wilson_high=0.0,
                )
            )
            continue
        mean_predicted = predicted_sum[position] / count
        observed = successes[position] / count
        wilson_low, wilson_high = _wilson_interval(successes[position], count)
        calibration_bins.append(
            CalibrationBin(
                low=low,
                high=high,
                count=count,
                mean_predicted=mean_predicted,
                observed=observed,
                wilson_low=wilson_low,
                wilson_high=wilson_high,
            )
        )
        if total_probabilities > 0:
            ece += (count / total_probabilities) * abs(mean_predicted - observed)

    return CalibrationReport(
        matches=matches,
        home_wins=home_wins,
        draws=draws,
        away_wins=away_wins,
        brier=brier,
        log_loss=log_loss,
        accuracy=accuracy,
        baseline_brier=baseline_brier,
        baseline_log_loss=baseline_log_loss,
        brier_skill=brier_skill,
        ece=ece,
        mean_xg_coverage=sum(item.xg_coverage for item in observations) / matches,
        bins=tuple(calibration_bins),
    )
