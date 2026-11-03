"""Utilitaires communs aux routes de l'API."""

from typing import NoReturn

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def conflict(message: str) -> NoReturn:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def commit_or_conflict(db: Session, message: str) -> None:
    """Valide la transaction et traduit une violation de contrainte en 409."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message) from exc


def not_found(message: str) -> NoReturn:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
