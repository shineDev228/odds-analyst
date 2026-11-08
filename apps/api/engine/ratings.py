"""Estimation des forces d'attaque et de défense d'une équipe de football.

Fonctions pures : aucune dépendance à la base de données, à FastAPI ou au réseau.
Le modèle est volontairement simple et explicable :

- chaque rencontre passée est pondérée par une demi-vie (les matchs récents
  comptent davantage) ;
- les forces sont régularisées vers la moyenne du championnat pour éviter les
  probabilités extrêmes sur un petit échantillon ;
- l'avantage du terrain est estimé sur les données, puis régularisé.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import sqrt


@dataclass(frozen=True)
class HistoricalMatch:
    """Rencontre terminée utilisée pour estimer les forces."""

    home_team_id: str
    away_team_id: str
    home_goals: int
    away_goals: int
    played_at: datetime

    def __post_init__(self) -> None:
        if self.home_goals < 0 or self.away_goals < 0:
            raise ValueError("Les scores historiques doivent être positifs ou nuls.")


@dataclass(frozen=True)
class RatingConfig:
    """Paramètres du modèle, alignés sur les préférences de l'utilisateur."""

    half_life_days: float = 240.0
    max_matches_per_team: int = 38
    min_matches_per_team: int = 3
    prior_matches: float = 5.0
    home_advantage_prior: float = 1.12
    away_advantage_prior: float = 0.90
    dixon_coles_rho: float = -0.05
    max_goals: int = 10
    simulations: int = 1000
    random_seed: int = 20261108
    totals_lines: tuple[float, ...] = (1.5, 2.5, 3.5)

    def __post_init__(self) -> None:
        if self.half_life_days <= 0:
            raise ValueError("La demi-vie doit être strictement positive.")
        if self.max_matches_per_team < 1:
            raise ValueError("Le nombre de matchs par équipe doit être positif.")
        if self.min_matches_per_team < 1:
            raise ValueError("Le minimum de matchs par équipe doit être positif.")
        if self.prior_matches < 0:
            raise ValueError("Le prior ne peut pas être négatif.")
        if self.max_goals < 1:
            raise ValueError("Le nombre maximal de buts doit être positif.")
        if self.simulations < 1:
            raise ValueError("Le nombre de simulations doit être positif.")
        if not self.totals_lines:
            raise ValueError("Au moins une ligne de total est nécessaire.")


@dataclass(frozen=True)
class TeamRating:
    """Force estimée d'une équipe et qualité de l'échantillon associé."""

    team_id: str
    attack: float
    defense: float
    goals_for_per_match: float
    goals_against_per_match: float
    matches: int
    effective_matches: float
    last_played_at: datetime | None
    sigma_attack: float
    sigma_defense: float


@dataclass(frozen=True)
class Ratings:
    """Résultat de l'estimation pour les deux équipes d'une rencontre."""

    league_average_goals: float
    home_factor: float
    away_factor: float
    home: TeamRating
    away: TeamRating
    home_lambda: float
    away_lambda: float


class InsufficientDataError(ValueError):
    """Historique trop court pour produire une estimation honnête."""

    def __init__(
        self,
        home_team_id: str,
        home_matches: int,
        away_team_id: str,
        away_matches: int,
        required: int,
    ) -> None:
        self.home_team_id = home_team_id
        self.home_matches = home_matches
        self.away_team_id = away_team_id
        self.away_matches = away_matches
        self.required = required
        super().__init__(
            "Historique insuffisant : au moins "
            f"{required} matchs terminés par équipe sont nécessaires."
        )


@dataclass
class _Sample:
    """Accumulateur pondéré pour une équipe."""

    goals_for: float = 0.0
    goals_against: float = 0.0
    weight: float = 0.0
    weight_squared: float = 0.0
    matches: int = 0
    last_played_at: datetime | None = field(default=None)

    def add(self, goals_for: int, goals_against: int, weight: float, played_at: datetime) -> None:
        self.goals_for += goals_for * weight
        self.goals_against += goals_against * weight
        self.weight += weight
        self.weight_squared += weight * weight
        self.matches += 1
        if self.last_played_at is None or played_at > self.last_played_at:
            self.last_played_at = played_at

    @property
    def effective_matches(self) -> float:
        if self.weight_squared <= 0:
            return 0.0
        return (self.weight * self.weight) / self.weight_squared


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _recency_weight(days: float, half_life_days: float) -> float:
    return 0.5 ** (max(days, 0.0) / half_life_days)


def _usable(match: HistoricalMatch, as_of: datetime) -> bool:
    return _as_utc(match.played_at) < as_of


def _sample_for_team(
    matches: Sequence[HistoricalMatch],
    team_id: str,
    as_of: datetime,
    config: RatingConfig,
) -> _Sample:
    played = [
        match
        for match in matches
        if _usable(match, as_of)
        and (match.home_team_id == team_id or match.away_team_id == team_id)
    ]
    played.sort(key=lambda match: _as_utc(match.played_at), reverse=True)

    sample = _Sample()
    for match in played[: config.max_matches_per_team]:
        played_at = _as_utc(match.played_at)
        days = (as_of - played_at).total_seconds() / 86_400.0
        weight = _recency_weight(days, config.half_life_days)
        is_home = match.home_team_id == team_id
        goals_for = match.home_goals if is_home else match.away_goals
        goals_against = match.away_goals if is_home else match.home_goals
        sample.add(goals_for, goals_against, weight, played_at)
    return sample


def _league_averages(
    matches: Sequence[HistoricalMatch], as_of: datetime, config: RatingConfig
) -> tuple[float, float, float, float, float]:
    """Moyenne de buts par équipe et par match, buts à domicile et à l'extérieur."""
    home_goals = 0.0
    away_goals = 0.0
    home_weight = 0.0
    away_weight = 0.0
    for match in matches:
        if not _usable(match, as_of):
            continue
        played_at = _as_utc(match.played_at)
        days = (as_of - played_at).total_seconds() / 86_400.0
        weight = _recency_weight(days, config.half_life_days)
        home_goals += match.home_goals * weight
        away_goals += match.away_goals * weight
        home_weight += weight
        away_weight += weight

    if home_weight <= 0 or away_weight <= 0:
        return 2.6, 1.4, 1.2, 0.0, 0.0

    home_average = home_goals / home_weight
    away_average = away_goals / away_weight
    league_average = (home_goals + away_goals) / (home_weight + away_weight)
    return league_average, home_average, away_average, home_weight, away_weight


def _sigma(effective_matches: float) -> float:
    """Écart-type approximatif de la force sur l'échelle logarithmique."""
    if effective_matches <= 0:
        return 0.85
    return _clamp(1.0 / sqrt(effective_matches), 0.08, 0.85)


def estimate_ratings(
    matches: Sequence[HistoricalMatch],
    *,
    home_team_id: str,
    away_team_id: str,
    as_of: datetime,
    config: RatingConfig | None = None,
    league_matches: Sequence[HistoricalMatch] | None = None,
) -> Ratings:
    """Estime les forces et les buts attendus des deux équipes.

    `matches` contient l'historique des deux équipes ; `league_matches` sert à
    calculer la moyenne du championnat (par défaut, le même historique).
    """
    config = config or RatingConfig()
    reference = _as_utc(as_of)

    home_sample = _sample_for_team(matches, home_team_id, reference, config)
    away_sample = _sample_for_team(matches, away_team_id, reference, config)

    if (
        home_sample.matches < config.min_matches_per_team
        or away_sample.matches < config.min_matches_per_team
    ):
        raise InsufficientDataError(
            home_team_id,
            home_sample.matches,
            away_team_id,
            away_sample.matches,
            config.min_matches_per_team,
        )

    pool = league_matches if league_matches is not None else matches
    league_average, home_average, away_average, home_weight, away_weight = _league_averages(
        pool, reference, config
    )
    if home_weight <= 0 or away_weight <= 0:
        # Aucun historique exploitable pour la moyenne : on retombe sur les
        # échantillons des deux équipes.
        league_average, home_average, away_average, home_weight, away_weight = _league_averages(
            matches, reference, config
        )

    prior_weight = max(config.prior_matches * 2.0, 1.0)
    home_factor = (
        (home_average * home_weight + config.home_advantage_prior * league_average * prior_weight)
        / (home_weight + prior_weight)
    ) / league_average
    away_factor = (
        (away_average * away_weight + config.away_advantage_prior * league_average * prior_weight)
        / (away_weight + prior_weight)
    ) / league_average
    home_factor = _clamp(home_factor, 0.85, 1.45)
    away_factor = _clamp(away_factor, 0.70, 1.15)

    def _attack(sample: _Sample) -> float:
        smoothed = (sample.goals_for + config.prior_matches * league_average) / (
            sample.weight + config.prior_matches
        )
        return smoothed / league_average

    def _defense(sample: _Sample) -> float:
        smoothed = (sample.goals_against + config.prior_matches * league_average) / (
            sample.weight + config.prior_matches
        )
        return smoothed / league_average

    home_attack = _attack(home_sample)
    home_defense = _defense(home_sample)
    away_attack = _attack(away_sample)
    away_defense = _defense(away_sample)

    home_lambda = _clamp(league_average * home_attack * away_defense * home_factor, 0.05, 6.0)
    away_lambda = _clamp(league_average * away_attack * home_defense * away_factor, 0.05, 6.0)

    home_rating = TeamRating(
        team_id=home_team_id,
        attack=home_attack,
        defense=home_defense,
        goals_for_per_match=home_sample.goals_for / home_sample.weight
        if home_sample.weight > 0
        else 0.0,
        goals_against_per_match=home_sample.goals_against / home_sample.weight
        if home_sample.weight > 0
        else 0.0,
        matches=home_sample.matches,
        effective_matches=home_sample.effective_matches,
        last_played_at=home_sample.last_played_at,
        sigma_attack=_sigma(home_sample.effective_matches),
        sigma_defense=_sigma(home_sample.effective_matches),
    )
    away_rating = TeamRating(
        team_id=away_team_id,
        attack=away_attack,
        defense=away_defense,
        goals_for_per_match=away_sample.goals_for / away_sample.weight
        if away_sample.weight > 0
        else 0.0,
        goals_against_per_match=away_sample.goals_against / away_sample.weight
        if away_sample.weight > 0
        else 0.0,
        matches=away_sample.matches,
        effective_matches=away_sample.effective_matches,
        last_played_at=away_sample.last_played_at,
        sigma_attack=_sigma(away_sample.effective_matches),
        sigma_defense=_sigma(away_sample.effective_matches),
    )

    return Ratings(
        league_average_goals=league_average,
        home_factor=home_factor,
        away_factor=away_factor,
        home=home_rating,
        away=away_rating,
        home_lambda=home_lambda,
        away_lambda=away_lambda,
    )
