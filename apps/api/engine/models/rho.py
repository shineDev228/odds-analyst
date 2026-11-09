"""Estimation régularisée du paramètre Dixon-Coles `rho`.

Module pur. `rho` corrige les probabilités des scores faibles (0-0, 1-0, 0-1,
1-1). L'estimation est volontairement simple : elle utilise les moyennes de
buts du bassin comme buts attendus de référence, parcourt une grille de valeurs
et retient celle qui maximise la vraisemblance pondérée des scores observés.
Un rétrécissement vers un prior protège les petits échantillons.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, log

from engine.models.poisson import score_matrix

MIN_LOG_PROBABILITY = 1e-12


@dataclass(frozen=True)
class RhoEstimate:
    """Valeur de `rho` retenue et diagnostic de l'estimation."""

    value: float
    raw: float
    effective_matches: float
    observations: int


def _effective_matches(observations: Sequence[tuple[int, int, float]]) -> float:
    weight = sum(weight for _, _, weight in observations if weight > 0 and isfinite(weight))
    weight_squared = sum(
        weight * weight for _, _, weight in observations if weight > 0 and isfinite(weight)
    )
    if weight_squared <= 0:
        return 0.0
    return (weight * weight) / weight_squared


def _log_likelihood(
    observations: Sequence[tuple[int, int, float]],
    *,
    lambda_home: float,
    lambda_away: float,
    rho: float,
    max_goals: int,
) -> float:
    matrix = score_matrix(
        lambda_home,
        lambda_away,
        max_goals=max_goals,
        rho=rho,
    ).probabilities
    total = 0.0
    limit = matrix.shape[0]
    for home_goals, away_goals, weight in observations:
        if weight <= 0 or not isfinite(weight):
            continue
        if home_goals >= limit or away_goals >= limit:
            probability = MIN_LOG_PROBABILITY
        else:
            probability = float(matrix[home_goals, away_goals])
        total += weight * log(max(probability, MIN_LOG_PROBABILITY))
    return total


def estimate_rho(
    observations: Sequence[tuple[int, int, float]],
    *,
    lambda_home: float,
    lambda_away: float,
    prior: float = -0.05,
    prior_matches: float = 30.0,
    minimum: float = -0.20,
    maximum: float = 0.15,
    step: float = 0.005,
    max_goals: int = 10,
) -> RhoEstimate:
    """Estime `rho` par vraisemblance, puis le rétrécit vers `prior`."""
    if minimum >= maximum:
        raise ValueError("Les bornes de rho sont invalides.")
    if step <= 0:
        raise ValueError("Le pas de recherche de rho doit être strictement positif.")
    if prior_matches < 0:
        raise ValueError("Le nombre de matchs du prior ne peut pas être négatif.")
    if prior < minimum or prior > maximum:
        raise ValueError("Le prior de rho doit être compris entre les bornes.")

    usable = [
        (home_goals, away_goals, weight)
        for home_goals, away_goals, weight in observations
        if weight > 0 and isfinite(weight)
    ]
    effective = _effective_matches(usable)
    if not usable or effective <= 0 or lambda_home <= 0 or lambda_away <= 0:
        return RhoEstimate(
            value=prior,
            raw=prior,
            effective_matches=0.0,
            observations=0,
        )

    steps = round((maximum - minimum) / step)
    best_rho = prior
    best_score = float("-inf")
    for index in range(steps + 1):
        candidate = minimum + index * step
        score = _log_likelihood(
            usable,
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            rho=candidate,
            max_goals=max_goals,
        )
        if score > best_score:
            best_score = score
            best_rho = candidate

    value = (effective * best_rho + prior_matches * prior) / (effective + prior_matches)
    value = max(minimum, min(maximum, value))
    return RhoEstimate(
        value=value,
        raw=best_rho,
        effective_matches=effective,
        observations=len(usable),
    )
