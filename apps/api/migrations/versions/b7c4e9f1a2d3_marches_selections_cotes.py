"""marches, selections et cotes

Revision ID: b7c4e9f1a2d3
Revises: 60be5c8acb53
Create Date: 2026-11-04 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c4e9f1a2d3"
down_revision: str | None = "60be5c8acb53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MARKET_SUBJECT = sa.Enum(
    "match",
    "team",
    "player",
    name="market_subject",
    native_enum=False,
    length=20,
)


def upgrade() -> None:
    op.create_table(
        "market_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("sport_code", sa.String(length=40), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("family", sa.String(length=80), nullable=False),
        sa.Column("period", sa.String(length=40), nullable=False),
        sa.Column("subject", MARKET_SUBJECT, nullable=False),
        sa.Column("line_kind", sa.String(length=20), nullable=False),
        sa.Column(
            "selection_templates",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "line_kind IN ('aucune', 'simple', 'double', 'intervalle', 'libre')",
            name="ck_market_template_line_kind",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        op.f("ix_market_templates_sport_code"), "market_templates", ["sport_code"], unique=False
    )
    op.create_index(
        op.f("ix_market_templates_family"), "market_templates", ["family"], unique=False
    )

    op.create_table(
        "markets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("template_code", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("family", sa.String(length=80), nullable=False),
        sa.Column("period", sa.String(length=40), nullable=False),
        sa.Column("subject", MARKET_SUBJECT, nullable=False),
        sa.Column("subject_team_id", sa.Uuid(), nullable=True),
        sa.Column("subject_player", sa.String(length=120), nullable=True),
        sa.Column("line", sa.Float(), nullable=True),
        sa.Column("line2", sa.Float(), nullable=True),
        sa.Column("signature", sa.String(length=64), nullable=False),
        sa.Column("is_custom", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_team_id"], ["teams.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "signature", name="uq_market_match_signature"),
    )
    op.create_index(op.f("ix_markets_match_id"), "markets", ["match_id"], unique=False)
    op.create_index(op.f("ix_markets_template_code"), "markets", ["template_code"], unique=False)
    op.create_index(op.f("ix_markets_family"), "markets", ["family"], unique=False)
    op.create_index(
        op.f("ix_markets_subject_team_id"), "markets", ["subject_team_id"], unique=False
    )

    op.create_table(
        "selections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("market_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("line", sa.Float(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_id", "code", name="uq_selection_market_code"),
    )
    op.create_index(op.f("ix_selections_market_id"), "selections", ["market_id"], unique=False)

    op.create_table(
        "odds_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("selection_id", sa.Uuid(), nullable=False),
        sa.Column("decimal_odds", sa.Float(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bookmaker", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("decimal_odds > 1", name="ck_odds_decimal_gt_one"),
        sa.ForeignKeyConstraint(["selection_id"], ["selections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_odds_snapshots_selection_id"), "odds_snapshots", ["selection_id"], unique=False
    )
    op.create_index(
        "ix_odds_selection_captured", "odds_snapshots", ["selection_id", "captured_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_odds_selection_captured", table_name="odds_snapshots")
    op.drop_index(op.f("ix_odds_snapshots_selection_id"), table_name="odds_snapshots")
    op.drop_table("odds_snapshots")
    op.drop_index(op.f("ix_selections_market_id"), table_name="selections")
    op.drop_table("selections")
    op.drop_index(op.f("ix_markets_subject_team_id"), table_name="markets")
    op.drop_index(op.f("ix_markets_family"), table_name="markets")
    op.drop_index(op.f("ix_markets_template_code"), table_name="markets")
    op.drop_index(op.f("ix_markets_match_id"), table_name="markets")
    op.drop_table("markets")
    op.drop_index(op.f("ix_market_templates_family"), table_name="market_templates")
    op.drop_index(op.f("ix_market_templates_sport_code"), table_name="market_templates")
    op.drop_table("market_templates")
