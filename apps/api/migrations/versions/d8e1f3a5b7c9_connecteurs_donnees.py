"""connecteurs de données

Revision ID: d8e1f3a5b7c9
Revises: c5d9e2f7a1b4
Create Date: 2026-11-09 12:00:00.000000

Migration strictement additive : nouvelles tables et colonnes facultatives,
aucune donnée existante n'est réécrite ni supprimée.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d8e1f3a5b7c9"
down_revision: str | None = "c5d9e2f7a1b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "provider_refs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("details", JSON_TYPE, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entity_type IN ('competition', 'season', 'team', 'match')",
            name="ck_provider_ref_entity_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "entity_type",
            "external_id",
            name="uq_provider_ref_external",
        ),
    )
    op.create_index(
        op.f("ix_provider_refs_provider"), "provider_refs", ["provider"], unique=False
    )
    op.create_index(
        op.f("ix_provider_refs_entity_type"),
        "provider_refs",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provider_refs_entity_id"),
        "provider_refs",
        ["entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_provider_ref_entity",
        "provider_refs",
        ["entity_type", "entity_id", "provider"],
        unique=False,
    )

    op.create_table(
        "connector_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("competition_id", sa.Uuid(), nullable=False),
        sa.Column("season_id", sa.Uuid(), nullable=False),
        sa.Column("external_league_id", sa.String(length=200), nullable=False),
        sa.Column("external_season", sa.String(length=40), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_fixtures_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_stats_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_odds_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider IN ('bigballsdata', 'the_odds_api', 'football_data')",
            name="ck_connector_link_provider",
        ),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "external_league_id",
            "external_season",
            name="uq_connector_link_external",
        ),
    )
    op.create_index(
        op.f("ix_connector_links_provider"),
        "connector_links",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_links_competition_id"),
        "connector_links",
        ["competition_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_links_season_id"),
        "connector_links",
        ["season_id"],
        unique=False,
    )

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("link_id", sa.Uuid(), nullable=True),
        sa.Column("params", JSON_TYPE, nullable=False),
        sa.Column("payload", JSON_TYPE, nullable=True),
        sa.Column("summary", JSON_TYPE, nullable=False),
        sa.Column("requests_used", sa.Integer(), nullable=False),
        sa.Column("credits_used", sa.Integer(), nullable=False),
        sa.Column("quota_remaining", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('preview', 'applied', 'partial', 'failed', 'expired', 'interrompue')",
            name="ck_sync_run_status",
        ),
        sa.ForeignKeyConstraint(["link_id"], ["connector_links.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sync_runs_provider"), "sync_runs", ["provider"], unique=False)
    op.create_index(op.f("ix_sync_runs_status"), "sync_runs", ["status"], unique=False)
    op.create_index(op.f("ix_sync_runs_link_id"), "sync_runs", ["link_id"], unique=False)

    op.create_table(
        "provider_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("period_kind", sa.String(length=10), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("limit", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("period_kind IN ('day', 'month')", name="ck_provider_usage_kind"),
        sa.CheckConstraint("used >= 0 AND \"limit\" >= 0", name="ck_provider_usage_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "period_kind",
            "period_start",
            name="uq_provider_usage_period",
        ),
    )
    op.create_index(
        op.f("ix_provider_usage_provider"),
        "provider_usage",
        ["provider"],
        unique=False,
    )

    op.add_column(
        "matches",
        sa.Column("data_source", sa.String(length=40), server_default="manual", nullable=False),
    )
    op.add_column(
        "matches",
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_matches_data_source"), "matches", ["data_source"], unique=False
    )

    op.add_column(
        "team_match_stats",
        sa.Column("data_source", sa.String(length=40), server_default="manual", nullable=False),
    )

    op.create_index(
        "ix_odds_selection_source_captured",
        "odds_snapshots",
        ["selection_id", "source", "captured_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_odds_selection_source_captured", table_name="odds_snapshots")
    op.drop_column("team_match_stats", "data_source")
    op.drop_index(op.f("ix_matches_data_source"), table_name="matches")
    op.drop_column("matches", "source_updated_at")
    op.drop_column("matches", "data_source")
    op.drop_index(op.f("ix_provider_usage_provider"), table_name="provider_usage")
    op.drop_table("provider_usage")
    op.drop_index(op.f("ix_sync_runs_link_id"), table_name="sync_runs")
    op.drop_index(op.f("ix_sync_runs_status"), table_name="sync_runs")
    op.drop_index(op.f("ix_sync_runs_provider"), table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index(op.f("ix_connector_links_season_id"), table_name="connector_links")
    op.drop_index(op.f("ix_connector_links_competition_id"), table_name="connector_links")
    op.drop_index(op.f("ix_connector_links_provider"), table_name="connector_links")
    op.drop_table("connector_links")
    op.drop_index("ix_provider_ref_entity", table_name="provider_refs")
    op.drop_index(op.f("ix_provider_refs_entity_id"), table_name="provider_refs")
    op.drop_index(op.f("ix_provider_refs_entity_type"), table_name="provider_refs")
    op.drop_index(op.f("ix_provider_refs_provider"), table_name="provider_refs")
    op.drop_table("provider_refs")
