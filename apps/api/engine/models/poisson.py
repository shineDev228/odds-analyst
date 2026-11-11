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


def score_matrices(
    home_lambdas: NDArray[np.float64],
    away_lambdas: NDArray[np.float64],
    *,
    max_goals: int = 10,
    rho: float = -0.05,
) -> NDArray[np.float64]:
    """Construit plusieurs matrices de scores en une passe.

    Résultat identique, ligne par ligne, à un appel répété de `score_matrix` :
    mêmes moyennes bornées, même correction Dixon-Coles, même renormalisation.
    L'usage groupé évite les surcoûts de NumPy sur de très petits tableaux.
    """
    if max_goals < 1:
        raise ValueError("Le nombre maximal de buts doit être positif.")
    home = np.clip(np.asarray(home_lambdas, dtype=np.float64), MIN_LAMBDA, MAX_LAMBDA)
    away = np.clip(np.asarray(away_lambdas, dtype=np.float64), MIN_LAMBDA, MAX_LAMBDA)
    if home.ndim != 1 or away.ndim != 1 or home.shape != away.shape:
        raise ValueError("Les moyennes de buts doivent être deux vecteurs de même taille.")
    if home.size == 0:
        raise ValueError("Au moins une moyenne de buts est nécessaire.")

    goals = np.arange(max_goals + 1, dtype=np.float64)
    division = np.array([factorial(goals_count) for goals_count in range(max_goals + 1)])
    home_pmf = np.exp(-home)[:, None] * np.power(home[:, None], goals) / division
    away_pmf = np.exp(-away)[:, None] * np.power(away[:, None], goals) / division

    matrices = home_pmf[:, :, None] * away_pmf[:, None, :]

    if rho != 0:
        matrices[:, 0, 0] *= 1.0 - home * away * rho
        matrices[:, 0, 1] *= 1.0 + home * rho
        matrices[:, 1, 0] *= 1.0 + away * rho
        matrices[:, 1, 1] *= 1.0 - rho
        np.clip(matrices, 0.0, None, out=matrices)

    totals = matrices.sum(axis=(1, 2))
    if np.any(totals <= 0):
        raise ValueError("La matrice des scores est vide.")
    matrices /= totals[:, None, None]
    return matrices
