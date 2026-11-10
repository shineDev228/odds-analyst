"""Connecteurs de données externes (calendrier, résultats, statistiques, cotes).

Le noyau (`base`, `http`, `quota`, `matching`) ne dépend ni de FastAPI ni des
modèles métier. Chaque adaptateur expose un client, un mapping pur et un
importateur.
"""

from app.connectors.base import (
    BudgetExceededError,
    ConnectorError,
    MissingKeyError,
    NormalizedEventOdds,
    NormalizedMarket,
    NormalizedMatch,
    NormalizedTeam,
    NormalizedTeamStats,
    PreviewCounts,
    ProviderAuthError,
    ProviderNotCoveredError,
    ProviderPayloadError,
    ProviderRateLimitError,
    QuotaInfo,
)

__all__ = [
    "BudgetExceededError",
    "ConnectorError",
    "MissingKeyError",
    "NormalizedEventOdds",
    "NormalizedMarket",
    "NormalizedMatch",
    "NormalizedTeam",
    "NormalizedTeamStats",
    "PreviewCounts",
    "ProviderAuthError",
    "ProviderNotCoveredError",
    "ProviderPayloadError",
    "ProviderRateLimitError",
    "QuotaInfo",
]
