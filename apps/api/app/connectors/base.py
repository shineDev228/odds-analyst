"""Types normalisés et erreurs communes aux connecteurs.

Ce module ne dépend ni de FastAPI, ni de SQLAlchemy : il décrit uniquement les
objets échangés entre les clients, le mapping et les importateurs.
"""

from dataclasses import dataclass, field
from datetime import datetime


class ConnectorError(Exception):
    """Erreur d'un connecteur, déjà formulée pour l'utilisateur."""

    status_code = 502

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class MissingKeyError(ConnectorError):
    """La clé du fournisseur n'est pas renseignée dans `.env`."""

    status_code = 503


class ProviderAuthError(ConnectorError):
    """Le fournisseur a refusé la clé."""

    status_code = 502


class ProviderRateLimitError(ConnectorError):
    """Le fournisseur a renvoyé 429 ou le budget local est épuisé."""

    status_code = 429


class ProviderNotCoveredError(ConnectorError):
    """Compétition, saison ou marché non couvert par le fournisseur."""

    status_code = 422


class ProviderPayloadError(ConnectorError):
    """Réponse illisible ou incomplète ; aucune écriture partielle."""

    status_code = 502


class BudgetExceededError(ProviderRateLimitError):
    """Le budget local restant est insuffisant pour l'appel demandé."""


@dataclass(slots=True)
class QuotaInfo:
    """État de quota renvoyé par un fournisseur ou calculé localement."""

    used: int = 0
    remaining: int | None = None
    limit: int | None = None
    reset_at: datetime | None = None


@dataclass(slots=True)
class NormalizedTeam:
    external_id: str
    name: str
    short_name: str | None = None


@dataclass(slots=True)
class NormalizedMatch:
    external_id: str
    competition_external_id: str
    season_label: str
    kickoff_at: datetime
    status: str
    home: NormalizedTeam
    away: NormalizedTeam
    home_score: int | None = None
    away_score: int | None = None
    half_time_home_score: int | None = None
    half_time_away_score: int | None = None
    venue: str | None = None
    raw_status: str | None = None


@dataclass(slots=True)
class NormalizedTeamStats:
    match_external_id: str
    team_external_id: str
    is_home: bool
    goals_for: int | None = None
    goals_against: int | None = None
    shots: int | None = None
    shots_on_target: int | None = None
    possession: float | None = None
    corners: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    expected_goals: float | None = None
    extra: dict[str, object] | None = None


@dataclass(slots=True)
class NormalizedMarket:
    """Un marché prêt à être écrit, issues exprimées en codes internes."""

    template_code: str
    outcomes: dict[str, float]
    line: float | None = None


@dataclass(slots=True)
class NormalizedEventOdds:
    """Cotes 1xBet d'un événement, déjà filtrées."""

    event_id: str
    home_team: str
    away_team: str
    commence_time: datetime
    bookmaker: str
    captured_at: datetime
    markets: list[NormalizedMarket] = field(default_factory=list)
    ignored: int = 0


@dataclass(slots=True)
class PreviewCounts:
    received: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    conflicts: int = 0
    ignored: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "received": self.received,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "conflicts": self.conflicts,
            "ignored": self.ignored,
        }
