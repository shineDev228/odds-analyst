"""Orchestration pure de la prédiction football v2.

Ce module relie les briques du moteur : forces, matrice de scores, marchés et
incertitude. Il ne connaît ni la base de données ni l'API.

La prédiction ponctuelle est séparée des intervalles Monte Carlo : le
rétro-test de calibration peut ainsi calculer rapidement des probabilités sans
simulation.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from engine.markets.football import MarketProbabilities, derive_probabilities
from engine.models.poisson import score_matrix
from engine.ratings import (
    HistoricalMatch,
    RatingConfig,
    Ratings,
    estimate_ratings,
)
from engine.uncertainty import Interval, SimulatedMarkets, simulate_markets

MODEL_VERSION = "football-poisson-v2"


@dataclass(frozen=True)
class Estimate:
    """Probabilité ponctuelle et fourchette d'une sélection."""

    code: str
    probability: float
    low: float
    high: float


@dataclass(frozen=True)
class TotalEstimate:
    """Estimations plus / moins pour une ligne."""

    line: float
    over: Estimate
    under: Estimate


@dataclass(frozen=True)
class ScorelineEstimate:
    """Score exact le plus probable."""

    home_goals: int
    away_goals: int
    probability: float


@dataclass(frozen=True)
class QualityAssessment:
    """Qualité statistique de l'échantillon."""

    level: str
    effective_matches: float
    matches_home: int
    matches_away: int
    xg_matches_home: int
    xg_matches_away: int
    xg_coverage_home: float
    xg_coverage_away: float


@dataclass(frozen=True)
class PointPrediction:
    """Probabilités sans intervalles, utilisées notamment pour la calibration."""

    ratings: Ratings
    markets: MarketProbabilities
    quality: QualityAssessment


@dataclass(frozen=True)
class FootballPrediction:
    """Sortie complète du moteur pour une rencontre."""

    expected_goals_home: float
    expected_goals_away: float
    ratings: Ratings
    markets: MarketProbabilities
    intervals: SimulatedMarkets
    resultat: tuple[Estimate, ...]
    double_chance: tuple[Estimate, ...]
    totaux: tuple[TotalEstimate, ...]
    btts: tuple[Estimate, ...]
    scores_exacts: tuple[ScorelineEstimate, ...]
    quality: QualityAssessment
    config: RatingConfig


def assess_quality(ratings: Ratings) -> QualityAssessment:
    """Détermine le niveau de fiabilité à partir de l'échantillon effectif."""
    effective = min(ratings.home.effective_matches, ratings.away.effective_matches)
    if effective < 5:
        level = "tres_faible"
    elif effective < 10:
        level = "faible"
    elif effective < 20:
        level = "moyenne"
    elif effective < 30:
        level = "correcte"
    else:
        level = "bonne"

    return QualityAssessment(
        level=level,
        effective_matches=effective,
        matches_home=ratings.home.matches,
        matches_away=ratings.away.matches,
        xg_matches_home=ratings.home.xg_matches,
        xg_matches_away=ratings.away.xg_matches,
        xg_coverage_home=ratings.home.xg_coverage,
        xg_coverage_away=ratings.away.xg_coverage,
    )


def _clamp_probability(value: float) -> float:
    return min(1.0, max(0.0, value))


def _estimate(code: str, probability: float, interval: Interval) -> Estimate:
    """Construit une estimation en élargissant la fourchette si nécessaire."""
    point = _clamp_probability(probability)
    low = min(_clamp_probability(interval.low), point)
    high = max(_clamp_probability(interval.high), point)
    return Estimate(code=code, probability=point, low=low, high=high)


def predict_point_football(
    matches: Sequence[HistoricalMatch],
    *,
    league_matches: Sequence[HistoricalMatch] | None,
    home_team_id: str,
    away_team_id: str,
    as_of: datetime,
    config: RatingConfig | None = None,
) -> PointPrediction:
    """Produit les probabilités ponctuelles, sans simulation d'incertitude."""
    config = config or RatingConfig()
    reference = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=UTC)

    ratings = estimate_ratings(
        matches,
        league_matches=league_matches,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        as_of=reference,
        config=config,
    )

    matrix = score_matrix(
        ratings.home_lambda,
        ratings.away_lambda,
        max_goals=config.max_goals,
        rho=ratings.dixon_coles_rho,
    )
    markets = derive_probabilities(
        matrix.probabilities,
        totals_lines=config.totals_lines,
    )
    return PointPrediction(
        ratings=ratings,
        markets=markets,
        quality=assess_quality(ratings),
    )


def predict_football(
    matches: Sequence[HistoricalMatch],
    *,
    league_matches: Sequence[HistoricalMatch] | None,
    home_team_id: str,
    away_team_id: str,
    as_of: datetime,
    config: RatingConfig | None = None,
) -> FootballPrediction:
    """Produit la prédiction complète, avec fourchettes d'incertitude."""
    config = config or RatingConfig()
    point = predict_point_football(
        matches,
        league_matches=league_matches,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        as_of=as_of,
        config=config,
    )
    ratings = point.ratings
    markets = point.markets
    intervals = simulate_markets(
        ratings,
        config,
        rho=ratings.dixon_coles_rho,
    )

    resultat = (
        _estimate("1", markets.home_win, intervals.home_win),
        _estimate("X", markets.draw, intervals.draw),
        _estimate("2", markets.away_win, intervals.away_win),
    )
    double_chance = (
        _estimate("1X", markets.home_or_draw, intervals.home_or_draw),
        _estimate("12", markets.home_or_away, intervals.home_or_away),
        _estimate("X2", markets.draw_or_away, intervals.draw_or_away),
    )
    totaux = tuple(
        TotalEstimate(
            line=total.line,
            over=_estimate("plus", total.over, simulated.over),
            under=_estimate("moins", total.under, simulated.under),
        )
        for total, simulated in zip(markets.totals, intervals.totals, strict=True)
    )
    btts = (
        _estimate("oui", markets.btts_yes, intervals.btts_yes),
        _estimate("non", markets.btts_no, intervals.btts_no),
    )
    scores_exacts = tuple(
        ScorelineEstimate(
            home_goals=score.home_goals,
            away_goals=score.away_goals,
            probability=score.probability,
        )
        for score in markets.scorelines
    )

    return FootballPrediction(
        expected_goals_home=ratings.home_lambda,
        expected_goals_away=ratings.away_lambda,
        ratings=ratings,
        markets=markets,
        intervals=intervals,
        resultat=resultat,
        double_chance=double_chance,
        totaux=totaux,
        btts=btts,
        scores_exacts=scores_exacts,
        quality=point.quality,
        config=config,
    )
