"""phase 15 etape 2 : suppression des tables de correspondance

Revision ID: e7b2d4c81f60
Revises: c3f6a9b2e5d8
Create Date: 2026-11-16 09:00:00.000000

L'identifiant BigBallsData est désormais stocké dans ``teams.external_id`` et
``matches.external_id``. Plus aucune table ne relie un objet interne à un
identifiant fournisseur :

- ``provider_refs`` : 283 lignes sur la base réelle, toutes reconstruites à
  partir du fournisseur ; la sauvegarde du 14/11 les contient encore ;
- ``connector_links`` : 6 lignes qui décrivaient les compétitions suivies ;
  la liste est maintenant une constante du service (``TRACKED_LEAGUES``) ;
- ``sync_runs.link_id`` : devenu inutile, chaque passe porte sa compétition
  dans ``params.league``.

Le retour arrière recrée les tables vides : les données de correspondance ne
sont pas reconstituables par la migration. Elles n'ont plus d'usage.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7b2d4c81f60"
down_revision: str | None = "c3f6a9b2e5d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

PROVIDERS = "'bigballsdata', 'the_odds_api', 'football_data', 'football_data_uk'"


def upgrade() -> None:
    # --- Journal : la colonne link_id disparaît avec sa clé et son index ----
    with op.batch_alter_table("sync_runs") as batch_op:
        batch_op.drop_index("ix_sync_runs_link_id")
        batch_op.drop_column("link_id")

    # --- Tables de correspondance ------------------------------------------
    op.drop_index("ix_connector_links_season_id", table_name="connector_links")
    op.drop_index("ix_connector_links_competition_id", table_name="connector_links")
    op.drop_index("ix_connector_links_provider", table_name="connector_links")
    op.drop_table("connector_links")

    op.drop_index("ix_provider_ref_entity", table_name="provider_refs")
    op.drop_index("ix_provider_refs_entity_id", table_name="provider_refs")
    op.drop_index("ix_provider_refs_entity_type", table_name="provider_refs")
    op.drop_index("ix_provider_refs_provider", table_name="provider_refs")
    op.drop_table("provider_refs")


def downgrade() -> None:
    # --- Tables de correspondance (vides) ----------------------------------
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
    op.create_index("ix_provider_refs_provider", "provider_refs", ["provider"], unique=False)
    op.create_index("ix_provider_refs_entity_type", "provider_refs", ["entity_type"], unique=False)
    op.create_index("ix_provider_refs_entity_id", "provider_refs", ["entity_id"], unique=False)
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
        sa.CheckConstraint(f"provider IN ({PROVIDERS})", name="ck_connector_link_provider"),
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
    op.create_index("ix_connector_links_provider", "connector_links", ["provider"], unique=False)
    op.create_index(
        "ix_connector_links_competition_id", "connector_links", ["competition_id"], unique=False
    )
    op.create_index(
        "ix_connector_links_season_id", "connector_links", ["season_id"], unique=False
    )

    # --- Journal : link_id revient ----------------------------------------
    with op.batch_alter_table("sync_runs") as batch_op:
        batch_op.add_column(sa.Column("link_id", sa.Uuid(), nullable=True))
        batch_op.create_index("ix_sync_runs_link_id", ["link_id"], unique=False)
        batch_op.create_foreign_key(
            "sync_runs_link_id_fkey",
            "connector_links",
            ["link_id"],
            ["id"],
            ondelete="SET NULL",
        )
