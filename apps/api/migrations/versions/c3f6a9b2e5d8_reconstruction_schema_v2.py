"""reconstruction bigballsdata : schema v2

Revision ID: c3f6a9b2e5d8
Revises: a4f1c8d2e965
Create Date: 2026-11-15 09:00:00.000000

Schéma de la reconstruction (phase 15, étape 1).

Migration additive : aucune donnée existante n'est réécrite. Les colonnes
ajoutées sont nullables, car la base courante contient encore des rencontres
saisies à la main et des rencontres issues du CSV, qui n'ont pas d'identifiant
BigBallsData. Les contraintes d'unicité laissent donc passer plusieurs valeurs
nulles, ce qui est le comportement attendu sur PostgreSQL comme sur SQLite.

Le retour arrière supprime exactement ce que cette révision a créé.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3f6a9b2e5d8"
down_revision: str | None = "a4f1c8d2e965"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATS_INTEGER_COLUMNS = (
    "shots_off_target",
    "blocked_shots",
    "shots_inside_box",
    "shots_outside_box",
    "fouls",
    "offsides",
    "goalkeeper_saves",
    "passes",
    "accurate_passes",
)


def upgrade() -> None:
    # --- Référentiel -----------------------------------------------------
    op.add_column("competitions", sa.Column("code", sa.String(length=40), nullable=True))
    op.create_unique_constraint("uq_competition_code", "competitions", ["code"])

    op.add_column("seasons", sa.Column("external_label", sa.String(length=40), nullable=True))

    op.add_column("teams", sa.Column("external_id", sa.String(length=200), nullable=True))
    op.add_column("teams", sa.Column("logo_url", sa.String(length=500), nullable=True))
    op.create_unique_constraint("uq_team_external_id", "teams", ["external_id"])

    # --- Rencontres ------------------------------------------------------
    op.add_column("matches", sa.Column("external_id", sa.String(length=200), nullable=True))
    op.add_column("matches", sa.Column("round_name", sa.String(length=80), nullable=True))
    op.add_column("matches", sa.Column("broadcast", sa.String(length=160), nullable=True))
    op.add_column("matches", sa.Column("attendance", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("has_odds", sa.Boolean(), nullable=True))
    op.create_unique_constraint("uq_match_external_id", "matches", ["external_id"])
    op.create_check_constraint(
        "ck_match_attendance_positive",
        "matches",
        "attendance IS NULL OR attendance >= 0",
    )

    # --- Statistiques d'équipe par rencontre -----------------------------
    for column in STATS_INTEGER_COLUMNS:
        op.add_column("team_match_stats", sa.Column(column, sa.Integer(), nullable=True))
    op.add_column("team_match_stats", sa.Column("pass_percentage", sa.Float(), nullable=True))
    op.create_check_constraint(
        "ck_stats_pass_percentage",
        "team_match_stats",
        "pass_percentage IS NULL OR (pass_percentage >= 0 AND pass_percentage <= 100)",
    )
    op.create_check_constraint(
        "ck_stats_counts_positive",
        "team_match_stats",
        "(shots IS NULL OR shots >= 0)"
        " AND (shots_on_target IS NULL OR shots_on_target >= 0)"
        " AND (shots_off_target IS NULL OR shots_off_target >= 0)"
        " AND (blocked_shots IS NULL OR blocked_shots >= 0)"
        " AND (shots_inside_box IS NULL OR shots_inside_box >= 0)"
        " AND (shots_outside_box IS NULL OR shots_outside_box >= 0)"
        " AND (corners IS NULL OR corners >= 0)"
        " AND (fouls IS NULL OR fouls >= 0)"
        " AND (offsides IS NULL OR offsides >= 0)"
        " AND (yellow_cards IS NULL OR yellow_cards >= 0)"
        " AND (red_cards IS NULL OR red_cards >= 0)"
        " AND (goalkeeper_saves IS NULL OR goalkeeper_saves >= 0)"
        " AND (passes IS NULL OR passes >= 0)"
        " AND (accurate_passes IS NULL OR accurate_passes >= 0)",
    )

    # --- Rattachement des lignes CSV -------------------------------------
    op.create_table(
        "csv_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "source",
            sa.String(length=40),
            server_default="football_data_uk",
            nullable=False,
        ),
        sa.Column("season_id", sa.Uuid(), nullable=False),
        sa.Column("row_key", sa.String(length=200), nullable=False),
        sa.Column("row_date", sa.Date(), nullable=False),
        sa.Column("home_team_name", sa.String(length=120), nullable=False),
        sa.Column("away_team_name", sa.String(length=120), nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("half_time_home_score", sa.Integer(), nullable=True),
        sa.Column("half_time_away_score", sa.Integer(), nullable=True),
        sa.Column("match_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("method", sa.String(length=20), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("margin", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=120), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
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
            "status IN ('applied', 'pending', 'ignored')",
            name="ck_csv_link_status",
        ),
        sa.CheckConstraint(
            "method IS NULL OR method IN ('score', 'name', 'manual')",
            name="ck_csv_link_method",
        ),
        sa.CheckConstraint(
            "(confidence IS NULL OR (confidence >= 0 AND confidence <= 1))"
            " AND (margin IS NULL OR (margin >= 0 AND margin <= 1))",
            name="ck_csv_link_scores",
        ),
        sa.CheckConstraint(
            "(home_score IS NULL OR home_score >= 0)"
            " AND (away_score IS NULL OR away_score >= 0)"
            " AND (half_time_home_score IS NULL OR half_time_home_score >= 0)"
            " AND (half_time_away_score IS NULL OR half_time_away_score >= 0)",
            name="ck_csv_link_goals_positive",
        ),
        sa.CheckConstraint(
            "status <> 'applied' OR match_id IS NOT NULL",
            name="ck_csv_link_applied_has_match",
        ),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "row_key", name="uq_csv_link_row"),
    )
    op.create_index(op.f("ix_csv_links_season_id"), "csv_links", ["season_id"], unique=False)
    op.create_index(op.f("ix_csv_links_match_id"), "csv_links", ["match_id"], unique=False)
    op.create_index(op.f("ix_csv_links_status"), "csv_links", ["status"], unique=False)
    op.create_index(
        "uq_csv_link_applied_match",
        "csv_links",
        ["match_id"],
        unique=True,
        postgresql_where=sa.text("status = 'applied'"),
    )

    # --- Rattachement des événements de cotes ----------------------------
    op.create_table(
        "odds_event_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider",
            sa.String(length=40),
            server_default="the_odds_api",
            nullable=False,
        ),
        sa.Column("event_id", sa.String(length=200), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("competition_code", sa.String(length=40), nullable=False),
        sa.Column("commence_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team_name", sa.String(length=120), nullable=False),
        sa.Column("away_team_name", sa.String(length=120), nullable=False),
        sa.Column(
            "method",
            sa.String(length=20),
            server_default="kickoff",
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("margin", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=120), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
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
            "method IN ('kickoff', 'name_fallback', 'manual')",
            name="ck_odds_event_link_method",
        ),
        sa.CheckConstraint(
            "(confidence IS NULL OR (confidence >= 0 AND confidence <= 1))"
            " AND (margin IS NULL OR (margin >= 0 AND margin <= 1))",
            name="ck_odds_event_link_scores",
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "event_id", name="uq_odds_event_link_event"),
    )
    op.create_index(
        op.f("ix_odds_event_links_match_id"),
        "odds_event_links",
        ["match_id"],
        unique=False,
    )
    op.create_index(
        "uq_odds_event_link_active_match",
        "odds_event_links",
        ["match_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_odds_event_link_active_match", table_name="odds_event_links")
    op.drop_index(op.f("ix_odds_event_links_match_id"), table_name="odds_event_links")
    op.drop_table("odds_event_links")

    op.drop_index("uq_csv_link_applied_match", table_name="csv_links")
    op.drop_index(op.f("ix_csv_links_status"), table_name="csv_links")
    op.drop_index(op.f("ix_csv_links_match_id"), table_name="csv_links")
    op.drop_index(op.f("ix_csv_links_season_id"), table_name="csv_links")
    op.drop_table("csv_links")

    op.drop_constraint("ck_stats_counts_positive", "team_match_stats", type_="check")
    op.drop_constraint("ck_stats_pass_percentage", "team_match_stats", type_="check")
    op.drop_column("team_match_stats", "pass_percentage")
    for column in reversed(STATS_INTEGER_COLUMNS):
        op.drop_column("team_match_stats", column)

    op.drop_constraint("ck_match_attendance_positive", "matches", type_="check")
    op.drop_constraint("uq_match_external_id", "matches", type_="unique")
    op.drop_column("matches", "has_odds")
    op.drop_column("matches", "attendance")
    op.drop_column("matches", "broadcast")
    op.drop_column("matches", "round_name")
    op.drop_column("matches", "external_id")

    op.drop_constraint("uq_team_external_id", "teams", type_="unique")
    op.drop_column("teams", "logo_url")
    op.drop_column("teams", "external_id")

    op.drop_column("seasons", "external_label")

    op.drop_constraint("uq_competition_code", "competitions", type_="unique")
    op.drop_column("competitions", "code")
