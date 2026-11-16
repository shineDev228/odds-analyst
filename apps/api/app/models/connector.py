"""Journal de synchronisation et compteurs de consommation.

Ces tables sont additives : elles ne modifient aucune donnée métier. Depuis la
phase 15, l'appartenance d'une équipe ou d'une rencontre à un fournisseur est
portée directement par ``teams.external_id`` et ``matches.external_id`` : les
tables de correspondance ont disparu.
"""

import enum
from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, TimestampMixin


class SyncStatus(enum.StrEnum):
    PREVIEW = "preview"
    APPLIED = "applied"
    PARTIAL = "partial"
    FAILED = "failed"
    EXPIRED = "expired"
    INTERRUPTED = "interrompue"


class SyncOperation(enum.StrEnum):
    # Passe de calendrier, résultats, statistiques et classements.
    FIXTURES = "fixtures"
    # Marchés des rencontres à venir (The Odds API, phase 15 étape 4).
    ODDS = "odds"


class SyncRun(Base, TimestampMixin):
    """Journal d'une passe de synchronisation, relisible sans appel réseau."""

    __tablename__ = "sync_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    params: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONType)
    summary: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    requests_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quota_remaining: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(String(1000))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('preview', 'applied', 'partial', 'failed', 'expired', 'interrompue')",
            name="ck_sync_run_status",
        ),
        # Le journal est lu du plus récent au plus ancien.
        Index("ix_sync_runs_created_at", "created_at"),
    )


class ProviderUsage(Base, TimestampMixin):
    """Compteur local de consommation, persisté entre deux démarrages."""

    __tablename__ = "provider_usage"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    period_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "provider", "period_kind", "period_start", name="uq_provider_usage_period"
        ),
        CheckConstraint("period_kind IN ('day', 'month')", name="ck_provider_usage_kind"),
        CheckConstraint("used >= 0 AND \"limit\" >= 0", name="ck_provider_usage_positive"),
    )
