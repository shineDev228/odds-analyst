"""Modèles ORM — l'import de ce module enregistre toutes les tables."""

from app.models.match import Match, MatchStatus, TeamMatchStats
from app.models.reference import Competition, Season, Sport, Team
from app.models.settings import AppSetting
from app.models.user import AuditLog, User, UserSession

__all__ = [
    "AppSetting",
    "AuditLog",
    "Competition",
    "Match",
    "MatchStatus",
    "Season",
    "Sport",
    "Team",
    "TeamMatchStats",
    "User",
    "UserSession",
]
