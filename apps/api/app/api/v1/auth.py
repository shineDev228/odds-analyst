"""Authentification de l'administrateur unique."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import deps
from app.core.config import settings
from app.core.security import hash_token
from app.models.user import User, UserSession
from app.schemas.auth import AuthStatus, BootstrapRequest, Credentials, UserRead
from app.services import audit
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["Authentification"])

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _session_user(db: Session, request: Request) -> User | None:
    raw = request.cookies.get(settings.session_cookie_name)
    if not raw:
        return None
    row = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(raw)))
    if row is None:
        return None
    if deps.as_utc(row.expires_at) <= datetime.now(UTC):
        return None
    user = db.get(User, row.user_id)
    return user if user and user.is_active else None


@router.get("/status", summary="État de l'installation et de la session")
def status_(request: Request, db: deps.DbSession) -> AuthStatus:
    user = _session_user(db, request)
    return AuthStatus(
        admin_configured=auth_service.admin_configured(db),
        authenticated=user is not None,
        user=UserRead.model_validate(user) if user else None,
    )


@router.post(
    "/bootstrap",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Créer le compte administrateur (première utilisation)",
)
def bootstrap(
    payload: BootstrapRequest, request: Request, response: Response, db: deps.DbSession
) -> User:
    if settings.is_production:
        client = request.client.host if request.client else ""
        if client not in _LOOPBACK:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Création initiale autorisée uniquement depuis la machine locale.",
            )

    user = auth_service.bootstrap_admin(db, str(payload.email), payload.password)
    token, csrf = auth_service.create_session(db, user, request)
    auth_service.set_auth_cookies(response, token, csrf)
    audit.record(db, "auth.bootstrap", user_id=user.id, entity="user", entity_id=str(user.id),
                 request=request)
    return user


@router.post("/login", response_model=UserRead, summary="Connexion")
def login(
    payload: Credentials, request: Request, response: Response, db: deps.DbSession
) -> User:
    user = auth_service.authenticate(db, str(payload.email), payload.password, request)
    auth_service.revoke_current_cookie_session(db, request)
    token, csrf = auth_service.create_session(db, user, request)
    auth_service.set_auth_cookies(response, token, csrf)
    audit.record(db, "auth.login", user_id=user.id, entity="user", entity_id=str(user.id),
                 request=request)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Déconnexion")
def logout(
    request: Request,
    response: Response,
    ctx: Annotated[deps.AuthContext, Depends(deps.get_auth_context)],
    _: Annotated[None, Depends(deps.verify_csrf)],
    db: deps.DbSession,
) -> None:
    raw = request.cookies.get(settings.session_cookie_name)
    if raw:
        auth_service.revoke_session(db, raw)
    auth_service.clear_auth_cookies(response)
    audit.record(db, "auth.logout", user_id=ctx.user.id, request=request)


@router.get("/me", response_model=UserRead, summary="Profil de l'utilisateur connecté")
def me(user: deps.CurrentUser) -> User:
    return user
