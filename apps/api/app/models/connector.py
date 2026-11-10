"""Journal, liens et références des connecteurs de données.

Ces tables sont additives : elles ne modifient aucune donnée métier existante.
Les références externes sont polymorphes (compétition, saison, équipe,
rencontre) et l'intégrité est assurée par les services et les tests.
"""

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin

if TYPE_CHECKING:
    from app.models.reference import Competition, Season


class RefEntity(enum.StrEnum):
    COMPETITION = "competition"
    SEASON = "season"
    TEAM = "team"
    MATCH = "match"


class SyncStatus(enum.StrEnum):
    PREVIEW = "preview"
    APPLIED = "applied"
    PARTIAL = "partial"
    FAILED = "failed"
    EXPIRED = "expired"
    INTERRUPTED = "interrompue"


class SyncOperation(enum.StrEnum):
    FIXTURES = "fixtures"
    STATS = "stats"
    RESULTS_STATS = "results_stats"
    ODDS = "odds"
    ODDS_EXTENDED = "odds_extended"
    EVENTS = "events"


PROVIDERS = ("bigballsdata", "the_odds_api", "football_data", "football_data_uk")


class ProviderRef(Base, TimestampMixin):
    """Association entre un objet interne et un identifiant fournisseur."""

    __tablename__ = "provider_refs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONType)

    __table_args__ = (
        UniqueConstraint(
            "provider", "entity_type", "external_id", name="uq_provider_ref_external"
        ),
        Index("ix_provider_ref_entity", "entity_type", "entity_id", "provider"),
        CheckConstraint(
            "entity_type IN ('competition', 'season', 'team', 'match')",
            name="ck_provider_ref_entity_type",
        ),
    )


class ConnectorLink(Base, TimestampMixin):
    """Compétition et saison internes suivies depuis un fournisseur."""

    __tablename__ = "connector_links"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    competition_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_league_id: Mapped[str] = mapped_column(String(200), nullable=False)
    external_season: Mapped[str] = mapped_column(String(40), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_fixtures_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_stats_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_odds_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    competition: Mapped["Competition"] = relationship()
    season: Mapped["Season"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_league_id",
            "external_season",
            name="uq_connector_link_external",
        ),
        CheckConstraint(
            "provider IN ('bigballsdata', 'the_odds_api', 'football_data', 'football_data_uk')",
            name="ck_connector_link_provider",
        ),
    )


class SyncRun(Base, TimestampMixin):
    """Aperçu ou journal d'une synchronisation."""

    __tablename__ = "sync_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    link_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("connector_links.id", ondelete="SET NULL"), index=True
    )
    params: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONType)
    summary: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    requests_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quota_remaining: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(String(1000))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    link: Mapped["ConnectorLink | None"] = relationship()

    __table_args__ = (
        CheckConstraint(
            "status IN ('preview', 'applied', 'partial', 'failed', 'expired', 'interrompue')",
            name="ck_sync_run_status",
        ),
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
