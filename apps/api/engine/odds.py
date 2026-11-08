"""Calculs de cotes — fonctions pures, sans dépendance applicative.

Toutes les cotes sont décimales (format européen) et strictement supérieures à 1.
Les probabilités sont exprimées entre 0 et 1.
"""

from collections.abc import Sequence

MIN_DECIMAL_ODDS = 1.0


class InvalidOddsError(ValueError):
    """Cote décimale invalide."""


def validate_odds(decimal_odds: float) -> float:
    """Vérifie qu'une cote décimale est exploitable."""
    if decimal_odds <= MIN_DECIMAL_ODDS:
        raise InvalidOddsError("Une cote décimale doit être strictement supérieure à 1.")
    return float(decimal_odds)


def implied_probability(decimal_odds: float) -> float:
    """Probabilité implicite brute d'une cote décimale (avant normalisation)."""
    return 1.0 / validate_odds(decimal_odds)


def implied_probabilities(odds: Sequence[float]) -> list[float]:
    """Probabilités implicites brutes de plusieurs cotes."""
    if not odds:
        raise InvalidOddsError("Au moins une cote est nécessaire.")
    return [implied_probability(value) for value in odds]


def overround(odds: Sequence[float]) -> float:
    """Marge du bookmaker : somme des probabilités implicites moins 1.

    Une valeur positive indique une marge en faveur du bookmaker.
    """
    return sum(implied_probabilities(odds)) - 1.0


def overround_percent(odds: Sequence[float]) -> float:
    """Marge exprimée en pourcentage."""
    return overround(odds) * 100.0


def fair_probabilities(odds: Sequence[float]) -> list[float]:
    """Probabilités normalisées dont la somme vaut 1."""
    probabilities = implied_probabilities(odds)
    total = sum(probabilities)
    if total <= 0:
        raise InvalidOddsError("La somme des probabilités doit être positive.")
    return [value / total for value in probabilities]


def fair_odds(odds: Sequence[float]) -> list[float]:
    """Cotes équitables correspondant aux probabilités normalisées.

    La marge du bookmaker est retirée proportionnellement.
    """
    return [1.0 / value for value in fair_probabilities(odds)]
