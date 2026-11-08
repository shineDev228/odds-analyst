"""Distribution des scores : Poisson bivarié avec correction Dixon-Coles.

Module pur, sans dépendance applicative. La matrice est tronquée au nombre
maximal de buts ; elle est renormalisée pour que la somme des probabilités
vaille exactement 1.
"""

from dataclasses import dataclass
from math import exp, factorial

import numpy as np
from numpy.typing import NDArray

MIN_LAMBDA = 0.01
MAX_LAMBDA = 8.0


@dataclass(frozen=True)
class ScoreMatrix:
    """Matrice des probabilités de score et buts attendus associés."""

    probabilities: NDArray[np.float64]
    home_lambda: float
    away_lambda: float
    max_goals: int


def poisson_probabilities(lam: float, max_goals: int) -> NDArray[np.float64]:
    """Probabilités d'observer 0..max_goals buts pour une moyenne donnée."""
    if lam <= 0:
        raise ValueError("La moyenne de buts doit être strictement positive.")
    return np.array(
        [exp(-lam) * lam**goals / factorial(goals) for goals in range(max_goals + 1)],
        dtype=np.float64,
    )


def score_matrix(
    home_lambda: float,
    away_lambda: float,
    *,
    max_goals: int = 10,
    rho: float = -0.05,
) -> ScoreMatrix:
    """Construit la matrice des scores avec la correction Dixon-Coles.

    `rho` négatif renforce légèrement les scores 0-0 et 1-1, et diminue les
    scores 0-1 et 1-0. `rho = 0` désactive la correction.
    """
    if max_goals < 1:
        raise ValueError("Le nombre maximal de buts doit être positif.")
    home_lambda = min(max(home_lambda, MIN_LAMBDA), MAX_LAMBDA)
    away_lambda = min(max(away_lambda, MIN_LAMBDA), MAX_LAMBDA)

    matrix = np.outer(
        poisson_probabilities(home_lambda, max_goals),
        poisson_probabilities(away_lambda, max_goals),
    )

    if rho != 0:
        matrix[0, 0] *= 1.0 - home_lambda * away_lambda * rho
        matrix[0, 1] *= 1.0 + home_lambda * rho
        matrix[1, 0] *= 1.0 + away_lambda * rho
        matrix[1, 1] *= 1.0 - rho
        np.clip(matrix, 0.0, None, out=matrix)

    total = float(matrix.sum())
    if total <= 0:
        raise ValueError("La matrice des scores est vide.")
    matrix /= total

    return ScoreMatrix(
        probabilities=matrix,
        home_lambda=home_lambda,
        away_lambda=away_lambda,
        max_goals=max_goals,
    )
