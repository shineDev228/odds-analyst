"""Modèles ORM — l'import de ce module enregistre toutes les tables."""

from app.models.combination import SavedCombination, SavedCombinationLeg
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
    "AppSetting",
    "AuditLog",
    "Competition",
    "Market",
    "MarketSubject",
    "MarketTemplate",
    "Match",
    "MatchStatus",
    "OddsSnapshot",
    "SavedCombination",
    "SavedCombinationLeg",
    "Season",
    "Selection",
    "Sport",
    "Team",
    "TeamMatchStats",
    "User",
    "UserSession",
]
