"""Modèles ORM — l'import de ce module enregistre toutes les tables."""

from app.models.combination import SavedCombination, SavedCombinationLeg
from app.models.connector import (
    PROVIDERS,
    ConnectorLink,
    ProviderRef,
    ProviderUsage,
    RefEntity,
    SyncOperation,
    SyncRun,
    SyncStatus,
)
from app.models.market import (
    Market,
    MarketSubject,
    MarketTemplate,
    OddsSnapshot,
    Selection,
)
from app.models.match import Match, MatchStatus, TeamMatchStats
from app.models.reference import Competition, Season, Sport, Team
from app.models.settings import AppSetting
from app.models.user import AuditLog, User, UserSession

__all__ = [
    "PROVIDERS",
    "AppSetting",
    "AuditLog",
    "Competition",
    "ConnectorLink",
    "Market",
    "MarketSubject",
    "MarketTemplate",
    "Match",
    "MatchStatus",
    "OddsSnapshot",
    "ProviderRef",
    "ProviderUsage",
    "RefEntity",
    "SavedCombination",
    "SavedCombinationLeg",
    "Season",
    "Selection",
    "Sport",
    "SyncOperation",
    "SyncRun",
    "SyncStatus",
    "Team",
    "TeamMatchStats",
    "User",
    "UserSession",
]
