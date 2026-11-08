"""Dérivation des marchés football à partir de la matrice des scores.

Fonctions pures : la matrice de scores est la seule entrée.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class TotalProbabilities:
    """Probabilités plus / moins / push pour une ligne de total."""

    line: float
    over: float
    under: float
    push: float


@dataclass(frozen=True)
class ScorelineProbability:
    """Probabilité d'un score exact."""

    home_goals: int
    away_goals: int
    probability: float


@dataclass(frozen=True)
class MarketProbabilities:
    """Probabilités des marchés principaux d'une rencontre."""

    home_win: float
    draw: float
    away_win: float
    home_or_draw: float
    home_or_away: float
    draw_or_away: float
    totals: tuple[TotalProbabilities, ...]
    btts_yes: float
    btts_no: float
    scorelines: tuple[ScorelineProbability, ...]


def derive_probabilities(
    matrix: NDArray[np.float64],
    *,
    totals_lines: Sequence[float] = (1.5, 2.5, 3.5),
    top_scores: int = 8,
) -> MarketProbabilities:
    """Calcule les marchés principaux à partir d'une matrice de scores."""
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("La matrice des scores doit être carrée.")
    if not totals_lines:
        raise ValueError("Au moins une ligne de total est nécessaire.")

    home_win = float(np.tril(matrix, -1).sum())
    draw = float(np.trace(matrix))
    away_win = float(np.triu(matrix, 1).sum())

    goals = np.add.outer(np.arange(matrix.shape[0]), np.arange(matrix.shape[1]))
    totals: list[TotalProbabilities] = []
    for line in totals_lines:
        over = float(matrix[goals > line].sum())
        under = float(matrix[goals < line].sum())
        push = float(matrix[np.isclose(goals, line)].sum())
        totals.append(TotalProbabilities(line=float(line), over=over, under=under, push=push))

    btts_yes = float(matrix[1:, 1:].sum())

    ranked = np.argsort(matrix.ravel())[::-1][: max(top_scores, 1)]
    scorelines = tuple(
        ScorelineProbability(
            home_goals=int(index // matrix.shape[1]),
            away_goals=int(index % matrix.shape[1]),
            probability=float(matrix.ravel()[index]),
        )
        for index in ranked
    )

    return MarketProbabilities(
        home_win=home_win,
        draw=draw,
        away_win=away_win,
        home_or_draw=home_win + draw,
        home_or_away=home_win + away_win,
        draw_or_away=draw + away_win,
        totals=tuple(totals),
        btts_yes=btts_yes,
        btts_no=1.0 - btts_yes,
        scorelines=scorelines,
    )
