"""Dépendances partagées : session de base, authentification, CSRF."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_token
from app.db.session import get_db
from app.models.user import User, UserSession
from app.services.auth import resolve_session

DbSession = Annotated[Session, Depends(get_db)]

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def as_utc(value: datetime) -> datetime:
    """Normalise une date en UTC (SQLite renvoie des dates naïves)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@dataclass(slots=True)
class AuthContext:
    user: User
    session: UserSession


def get_auth_context(request: Request, db: DbSession) -> AuthContext:
    """Résout l'utilisateur à partir du cookie de session."""
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Connexion requise.")

    row, reason = resolve_session(db, raw_token)
    if row is None:
        detail = {
            "expired": "Session expirée.",
            "idle": "Session fermée après une longue inactivité. Reconnectez-vous.",
            "invalid": "Session invalide.",
        }[reason]
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Compte désactivé.")

    return AuthContext(user=user, session=row)


def get_current_user(ctx: Annotated[AuthContext, Depends(get_auth_context)]) -> User:
    return ctx.user


CurrentAuth = Annotated[AuthContext, Depends(get_auth_context)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def verify_csrf(request: Request, ctx: CurrentAuth) -> None:
    """Double soumission : l'en-tête doit correspondre au jeton de la session."""
    if request.method in SAFE_METHODS:
        return

    header = request.headers.get("X-CSRF-Token")
    cookie = request.cookies.get(settings.csrf_cookie_name)
    if not header or not cookie or header != cookie:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Jeton de sécurité absent ou invalide. Rechargez la page.",
        )
    if hash_token(header) != ctx.session.csrf_hash:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Jeton de sécurité invalide. Rechargez la page.",
        )
