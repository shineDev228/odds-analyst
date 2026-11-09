"""historique des combinaisons

Revision ID: c5d9e2f7a1b4
Revises: b7c4e9f1a2d3
Create Date: 2026-11-08 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5d9e2f7a1b4"
down_revision: str | None = "b7c4e9f1a2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "saved_combinations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("nombre_selections", sa.Integer(), nullable=False),
        sa.Column("cote_min", sa.Float(), nullable=False),
        sa.Column("cote_max", sa.Float(), nullable=False),
        sa.Column("marches_autorises", JSON_TYPE, nullable=False),
        sa.Column("total_odds", sa.Float(), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("expected_value", sa.Float(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
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
            "nombre_selections BETWEEN 2 AND 15",
            name="ck_saved_combination_nombre_selections",
        ),
        sa.CheckConstraint(
            "cote_min > 1 AND cote_max > cote_min",
            name="ck_saved_combination_odds_range",
        ),
        sa.CheckConstraint("total_odds > 1", name="ck_saved_combination_total_odds"),
        sa.CheckConstraint(
            "probability >= 0 AND probability <= 1",
            name="ck_saved_combination_probability",
        ),
        sa.CheckConstraint(
            "low >= 0 AND high <= 1 AND low <= probability AND probability <= high",
            name="ck_saved_combination_interval",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "fingerprint",
            name="uq_saved_combination_user_fingerprint",
        ),
    )
    op.create_index(
        op.f("ix_saved_combinations_user_id"),
        "saved_combinations",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "saved_combination_legs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("combination_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=True),
        sa.Column("market_id", sa.Uuid(), nullable=True),
        sa.Column("selection_id", sa.Uuid(), nullable=True),
        sa.Column("match_label", sa.String(length=240), nullable=False),
        sa.Column("competition_name", sa.String(length=160), nullable=False),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("market_name", sa.String(length=160), nullable=False),
        sa.Column("market_family", sa.String(length=80), nullable=False),
        sa.Column("market_period", sa.String(length=40), nullable=False),
        sa.Column("selection_code", sa.String(length=80), nullable=False),
        sa.Column("selection_label", sa.String(length=120), nullable=False),
        sa.Column("line", sa.Float(), nullable=True),
        sa.Column("decimal_odds", sa.Float(), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
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
        sa.CheckConstraint("position >= 0", name="ck_saved_combination_leg_position"),
        sa.CheckConstraint(
            "decimal_odds > 1",
            name="ck_saved_combination_leg_decimal_odds",
        ),
        sa.CheckConstraint(
            "probability >= 0 AND probability <= 1",
            name="ck_saved_combination_leg_probability",
        ),
        sa.ForeignKeyConstraint(
            ["combination_id"],
            ["saved_combinations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["selection_id"], ["selections.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "combination_id",
            "position",
            name="uq_saved_combination_leg_position",
        ),
        sa.UniqueConstraint(
            "combination_id",
            "match_id",
            name="uq_saved_combination_leg_match",
        ),
    )
    op.create_index(
        op.f("ix_saved_combination_legs_combination_id"),
        "saved_combination_legs",
        ["combination_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_saved_combination_legs_match_id"),
        "saved_combination_legs",
        ["match_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_saved_combination_legs_market_id"),
        "saved_combination_legs",
        ["market_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_saved_combination_legs_selection_id"),
        "saved_combination_legs",
        ["selection_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_saved_combination_legs_selection_id"),
        table_name="saved_combination_legs",
    )
    op.drop_index(
        op.f("ix_saved_combination_legs_market_id"),
        table_name="saved_combination_legs",
    )
    op.drop_index(
        op.f("ix_saved_combination_legs_match_id"),
        table_name="saved_combination_legs",
    )
    op.drop_index(
        op.f("ix_saved_combination_legs_combination_id"),
        table_name="saved_combination_legs",
    )
    op.drop_table("saved_combination_legs")
    op.drop_index(
        op.f("ix_saved_combinations_user_id"),
        table_name="saved_combinations",
    )
    op.drop_table("saved_combinations")
