"""Modèles ORM — l'import de ce module enregistre toutes les tables."""

from app.models.combination import SavedCombination, SavedCombinationLeg
from app.models.connector import (
    ProviderUsage,
    SyncOperation,
    SyncRun,
    SyncStatus,
)
from app.models.link import CsvLink, OddsEventLink
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
from app.models.snapshot import MarketBoardSnapshot, StandingsSnapshot, TeamSnapshot
from app.models.user import AuditLog, User, UserSession

__all__ = [
    "AppSetting",
    "AuditLog",
    "Competition",
    "CsvLink",
    "Market",
    "MarketBoardSnapshot",
    "MarketSubject",
    "MarketTemplate",
    "Match",
    "MatchStatus",
    "OddsEventLink",
    "OddsSnapshot",
    "ProviderUsage",
    "SavedCombination",
    "SavedCombinationLeg",
    "Season",
    "Selection",
    "Sport",
    "StandingsSnapshot",
    "SyncOperation",
    "SyncRun",
    "SyncStatus",
    "Team",
    "TeamMatchStats",
    "TeamSnapshot",
    "User",
    "UserSession",
]
