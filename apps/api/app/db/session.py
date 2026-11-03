"""Connexion à la base de données PostgreSQL."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Fournit une session de base de données par requête HTTP."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
