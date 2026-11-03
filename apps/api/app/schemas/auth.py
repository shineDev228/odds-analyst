"""Schémas d'authentification."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import password_policy_error
from app.schemas.common import ORMModel


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class BootstrapRequest(Credentials):
    @field_validator("password")
    @classmethod
    def _check_policy(cls, value: str) -> str:
        error = password_policy_error(value)
        if error:
            raise ValueError(error)
        return value


class UserRead(ORMModel):
    id: UUID
    email: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class AuthStatus(BaseModel):
    """État de l'installation, consultable sans être connecté."""

    admin_configured: bool
    authenticated: bool
    user: UserRead | None = None
