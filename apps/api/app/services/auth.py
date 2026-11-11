"""Authentification : amorçage, connexion, sessions, limitation des tentatives."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    generate_token,
    hash_password,
    hash_token,
    needs_rehash,
    password_policy_error,
    verify_password,
)
from app.models.user import User, UserSession


def _as_utc(value: datetime) -> datetime:
    """Normalise une date en UTC (SQLite renvoie des dates naïves)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@dataclass
class _Attempts:
    count: int = 0
    first_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    blocked_until: datetime | None = None


class LoginRateLimiter:
    """Limitation en mémoire, suffisante pour un utilisateur unique.

    Non partagée entre processus : à remplacer par Redis si l'API est
    un jour déployée en plusieurs instances.
    """

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self._max = max_attempts
        self._window = timedelta(seconds=window_seconds)
        self._entries: dict[str, _Attempts] = {}
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = datetime.now(UTC)
        with self._lock:
            entry = self._entries.get(key)
            if entry and entry.blocked_until and entry.blocked_until > now:
                remaining = int((entry.blocked_until - now).total_seconds())
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        "Trop de tentatives de connexion. "
                        f"Réessayez dans {max(1, remaining // 60)} minute(s)."
                    ),
                )
            if entry and now - entry.first_at > self._window:
                self._entries.pop(key, None)

    def register_failure(self, key: str) -> None:
        now = datetime.now(UTC)
        with self._lock:
            entry = self._entries.setdefault(key, _Attempts(first_at=now))
            entry.count += 1
            if entry.count >= self._max:
                entry.blocked_until = now + self._window

    def reset(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)


limiter = LoginRateLimiter(settings.login_max_attempts, settings.login_window_seconds)


def admin_configured(db: Session) -> bool:
    return (db.scalar(select(func.count()).select_from(User)) or 0) > 0


def bootstrap_admin(db: Session, email: str, password: str) -> User:
    if admin_configured(db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un administrateur existe déjà. Utilisez la page de connexion.",
        )
    error = password_policy_error(password)
    if error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error)

    user = User(email=email.lower(), password_hash=hash_password(password), is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str, request: Request) -> User:
    client = request.client.host if request.client else "inconnu"
    key = f"{client}:{email.lower()}"
    limiter.check(key)

    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not user.is_active or not verify_password(user.password_hash, password):
        limiter.register_failure(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Adresse électronique ou mot de passe incorrect.",
        )

    limiter.reset(key)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.last_login_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def resolve_session(db: Session, raw_token: str) -> tuple[UserSession | None, str]:
    """Valide une session : expiration absolue puis inactivité.

    Retourne `(session, état)` avec un état parmi `ok`, `invalid`, `expired`
    ou `idle`. Les sessions périmées sont supprimées immédiatement.
    """
    row = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(raw_token)))
    if row is None:
        return None, "invalid"

    now = datetime.now(UTC)
    if _as_utc(row.expires_at) <= now:
        db.delete(row)
        db.commit()
        return None, "expired"

    if now - _as_utc(row.last_seen_at) > timedelta(seconds=settings.session_idle_seconds):
        db.delete(row)
        db.commit()
        return None, "idle"

    if (now - _as_utc(row.last_seen_at)).total_seconds() >= settings.session_touch_seconds:
        row.last_seen_at = now
        db.commit()

    return row, "ok"


def create_session(db: Session, user: User, request: Request) -> tuple[str, str]:
    token = generate_token()
    csrf = generate_token()
    now = datetime.now(UTC)
    row = UserSession(
        token_hash=hash_token(token),
        csrf_hash=hash_token(csrf),
        user_id=user.id,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.session_max_age_seconds),
        last_seen_at=now,
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
    )
    db.add(row)
    db.commit()
    return token, csrf


def revoke_session(db: Session, token: str) -> None:
    row = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if row is not None:
        db.delete(row)
        db.commit()


def revoke_current_cookie_session(db: Session, request: Request) -> None:
    """Supprime la session portée par le cookie de la requête, si elle existe."""
    raw = request.cookies.get(settings.session_cookie_name)
    if raw:
        revoke_session(db, raw)


def purge_expired_sessions(db: Session) -> int:
    """Supprime les sessions expirées ou inactives depuis trop longtemps."""
    now = datetime.now(UTC)
    idle_limit = now - timedelta(seconds=settings.session_idle_seconds)
    result = (
        db.query(UserSession)
        .filter((UserSession.expires_at < now) | (UserSession.last_seen_at < idle_limit))
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(result or 0)


def set_auth_cookies(response: Response, token: str, csrf: str) -> None:
    max_age = settings.session_max_age_seconds
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf,
        max_age=max_age,
        httponly=False,
        samesite="strict",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
