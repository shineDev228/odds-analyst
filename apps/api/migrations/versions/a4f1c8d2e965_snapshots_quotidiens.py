"""snapshots quotidiens bigballsdata

Revision ID: a4f1c8d2e965
Revises: a1b2c3d4e5f6
Create Date: 2026-11-14 12:00:00.000000

Migration strictement additive : trois tables de snapshots, aucun accès aux
tables existantes n'est modifié. Le retour arrière supprime uniquement ces
trois tables, créées par cette révision.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4f1c8d2e965"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "team_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("captured_on", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("elo_rating", sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column("elo_games_counted", sa.Integer(), nullable=True),
        sa.Column("elo_last_match_date", sa.Date(), nullable=True),
        sa.Column("matches_played", sa.Integer(), nullable=True),
        sa.Column("btts_rate", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("over_2_5_rate", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("goals_scored", sa.Integer(), nullable=True),
        sa.Column("goals_conceded", sa.Integer(), nullable=True),
        sa.Column("clean_sheets", sa.Integer(), nullable=True),
        sa.Column("form_string", sa.String(length=10), nullable=True),
        sa.Column("home_wins", sa.Integer(), nullable=True),
        sa.Column("home_draws", sa.Integer(), nullable=True),
        sa.Column("home_losses", sa.Integer(), nullable=True),
        sa.Column("away_wins", sa.Integer(), nullable=True),
        sa.Column("away_draws", sa.Integer(), nullable=True),
        sa.Column("away_losses", sa.Integer(), nullable=True),
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
            "(btts_rate IS NULL OR (btts_rate >= 0 AND btts_rate <= 1))"
            " AND (over_2_5_rate IS NULL OR (over_2_5_rate >= 0 AND over_2_5_rate <= 1))",
            name="ck_team_snapshot_rates",
        ),
        sa.CheckConstraint(
            "(matches_played IS NULL OR matches_played >= 0)"
            " AND (elo_games_counted IS NULL OR elo_games_counted >= 0)"
            " AND (goals_scored IS NULL OR goals_scored >= 0)"
            " AND (goals_conceded IS NULL OR goals_conceded >= 0)"
            " AND (clean_sheets IS NULL OR clean_sheets >= 0)"
            " AND (home_wins IS NULL OR home_wins >= 0)"
            " AND (home_draws IS NULL OR home_draws >= 0)"
            " AND (home_losses IS NULL OR home_losses >= 0)"
            " AND (away_wins IS NULL OR away_wins >= 0)"
            " AND (away_draws IS NULL OR away_draws >= 0)"
            " AND (away_losses IS NULL OR away_losses >= 0)",
            name="ck_team_snapshot_counts",
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "captured_on", name="uq_team_snapshot_day"),
    )
    op.create_index(
        op.f("ix_team_snapshots_team_id"), "team_snapshots", ["team_id"], unique=False
    )
    op.create_index(
        op.f("ix_team_snapshots_captured_on"),
        "team_snapshots",
        ["captured_on"],
        unique=False,
    )

    op.create_table(
        "standings_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("competition_id", sa.Uuid(), nullable=False),
        sa.Column("season_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("captured_on", sa.Date(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("played", sa.Integer(), nullable=True),
        sa.Column("wins", sa.Integer(), nullable=True),
        sa.Column("draws", sa.Integer(), nullable=True),
        sa.Column("losses", sa.Integer(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("goals_for", sa.Integer(), nullable=True),
        sa.Column("goals_against", sa.Integer(), nullable=True),
        sa.Column("form_string", sa.String(length=10), nullable=True),
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
            "(rank IS NULL OR rank >= 1)"
            " AND (played IS NULL OR played >= 0)"
            " AND (wins IS NULL OR wins >= 0)"
            " AND (draws IS NULL OR draws >= 0)"
            " AND (losses IS NULL OR losses >= 0)"
            " AND (points IS NULL OR points >= 0)"
            " AND (goals_for IS NULL OR goals_for >= 0)"
            " AND (goals_against IS NULL OR goals_against >= 0)",
            name="ck_standings_snapshot_values",
        ),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team_id", "season_id", "captured_on", name="uq_standings_snapshot_day"
        ),
    )
    op.create_index(
        op.f("ix_standings_snapshots_competition_id"),
        "standings_snapshots",
        ["competition_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_standings_snapshots_season_id"),
        "standings_snapshots",
        ["season_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_standings_snapshots_team_id"),
        "standings_snapshots",
        ["team_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_standings_snapshots_captured_on"),
        "standings_snapshots",
        ["captured_on"],
        unique=False,
    )
    op.create_index(
        "ix_standings_snapshot_season_day",
        "standings_snapshots",
        ["season_id", "captured_on"],
        unique=False,
    )

    op.create_table(
        "market_board_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("external_match_id", sa.String(length=100), nullable=False),
        sa.Column("captured_on", sa.Date(), nullable=False),
        sa.Column("snapshot_slot", sa.String(length=10), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("odds_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("books_count", sa.Integer(), nullable=True),
        sa.Column("home_decimal", sa.Numeric(precision=7, scale=3), nullable=True),
        sa.Column("away_decimal", sa.Numeric(precision=7, scale=3), nullable=True),
        sa.Column("total_line", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("over_decimal", sa.Numeric(precision=7, scale=3), nullable=True),
        sa.Column("under_decimal", sa.Numeric(precision=7, scale=3), nullable=True),
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
            "snapshot_slot IN ('morning', 'evening')",
            name="ck_market_board_slot",
        ),
        sa.CheckConstraint(
            "(books_count IS NULL OR books_count >= 0)"
            " AND (home_decimal IS NULL OR home_decimal > 1)"
            " AND (away_decimal IS NULL OR away_decimal > 1)"
            " AND (total_line IS NULL OR total_line >= 0)"
            " AND (over_decimal IS NULL OR over_decimal > 1)"
            " AND (under_decimal IS NULL OR under_decimal > 1)",
            name="ck_market_board_values",
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "match_id", "captured_on", "snapshot_slot", name="uq_market_board_snapshot_slot"
        ),
    )
    op.create_index(
        op.f("ix_market_board_snapshots_match_id"),
        "market_board_snapshots",
        ["match_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_market_board_snapshots_captured_on"),
        "market_board_snapshots",
        ["captured_on"],
        unique=False,
    )
    op.create_index(
        "ix_market_board_snapshot_day_slot",
        "market_board_snapshots",
        ["captured_on", "snapshot_slot"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_board_snapshot_day_slot", table_name="market_board_snapshots"
    )
    op.drop_index(
        op.f("ix_market_board_snapshots_captured_on"),
        table_name="market_board_snapshots",
    )
    op.drop_index(
        op.f("ix_market_board_snapshots_match_id"), table_name="market_board_snapshots"
    )
    op.drop_table("market_board_snapshots")

    op.drop_index("ix_standings_snapshot_season_day", table_name="standings_snapshots")
    op.drop_index(
        op.f("ix_standings_snapshots_captured_on"), table_name="standings_snapshots"
    )
    op.drop_index(op.f("ix_standings_snapshots_team_id"), table_name="standings_snapshots")
    op.drop_index(op.f("ix_standings_snapshots_season_id"), table_name="standings_snapshots")
    op.drop_index(
        op.f("ix_standings_snapshots_competition_id"), table_name="standings_snapshots"
    )
    op.drop_table("standings_snapshots")

    op.drop_index(op.f("ix_team_snapshots_captured_on"), table_name="team_snapshots")
    op.drop_index(op.f("ix_team_snapshots_team_id"), table_name="team_snapshots")
    op.drop_table("team_snapshots")
