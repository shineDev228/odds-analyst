"""Fourchettes d'incertitude par simulation Monte Carlo.

Les forces estimées sont elles-mêmes incertaines. On simule des forces
log-normales dont l'écart-type dépend de l'échantillon effectif, puis on
recalcule les probabilités de chaque marché. Les percentiles 10 et 90 donnent
une fourchette à 80 %.

La graine est fixe : un même historique produit exactement les mêmes
fourchettes. Le module reste pur.
"""

from dataclasses import dataclass

import numpy as np

from engine.models.poisson import score_matrix
from engine.ratings import RatingConfig, Ratings

LEAGUE_SIGMA = 0.05
HOME_SIGMA = 0.04


@dataclass(frozen=True)
class Interval:
    """Fourchette d'une probabilité."""

    low: float
    median: float
    high: float


@dataclass(frozen=True)
class SimulatedTotal:
    """Fourchette plus / moins pour une ligne de total."""

    line: float
    over: Interval
    under: Interval


@dataclass(frozen=True)
class SimulatedMarkets:
    """Fourchettes des marchés principaux."""

    home_win: Interval
    draw: Interval
    away_win: Interval
    home_or_draw: Interval
    home_or_away: Interval
    draw_or_away: Interval
    totals: tuple[SimulatedTotal, ...]
    btts_yes: Interval
    btts_no: Interval


def _interval(values: np.ndarray) -> Interval:
    low, median, high = np.percentile(values, [10.0, 50.0, 90.0])
    return Interval(low=float(low), median=float(median), high=float(high))


def simulate_markets(
    ratings: Ratings,
    config: RatingConfig,
    *,
    simulations: int | None = None,
    seed: int | None = None,
) -> SimulatedMarkets:
    """Simule les probabilités et retourne leurs percentiles 10-90."""
    draws = simulations if simulations is not None else config.simulations
    if draws < 1:
        raise ValueError("Le nombre de simulations doit être positif.")

    rng = np.random.default_rng(config.random_seed if seed is None else seed)

    home = np.empty(draws)
    draw = np.empty(draws)
    away = np.empty(draws)
    btts = np.empty(draws)
    totals_over = np.empty((len(config.totals_lines), draws))
    goals = np.add.outer(np.arange(config.max_goals + 1), np.arange(config.max_goals + 1))

    for index in range(draws):
        global_factor = np.exp(rng.normal(0.0, LEAGUE_SIGMA))
        home_boost = np.exp(rng.normal(0.0, HOME_SIGMA))
        home_attack = np.exp(rng.normal(0.0, ratings.home.sigma_attack))
        home_defense = np.exp(rng.normal(0.0, ratings.home.sigma_defense))
        away_attack = np.exp(rng.normal(0.0, ratings.away.sigma_attack))
        away_defense = np.exp(rng.normal(0.0, ratings.away.sigma_defense))

        home_lambda = ratings.home_lambda * home_attack * away_defense * global_factor * home_boost
        away_lambda = ratings.away_lambda * away_attack * home_defense * global_factor
        matrix = score_matrix(
            float(home_lambda),
            float(away_lambda),
            max_goals=config.max_goals,
            rho=config.dixon_coles_rho,
        ).probabilities

        home[index] = np.tril(matrix, -1).sum()
        draw[index] = np.trace(matrix)
        away[index] = np.triu(matrix, 1).sum()
        btts[index] = matrix[1:, 1:].sum()
        for position, line in enumerate(config.totals_lines):
            totals_over[position, index] = matrix[goals > line].sum()

    totals = tuple(
        SimulatedTotal(
            line=float(line),
            over=_interval(totals_over[position]),
            under=_interval(1.0 - totals_over[position]),
        )
        for position, line in enumerate(config.totals_lines)
    )

    return SimulatedMarkets(
        home_win=_interval(home),
        draw=_interval(draw),
        away_win=_interval(away),
        home_or_draw=_interval(home + draw),
        home_or_away=_interval(home + away),
        draw_or_away=_interval(draw + away),
        totals=totals,
        btts_yes=_interval(btts),
        btts_no=_interval(1.0 - btts),
    )
