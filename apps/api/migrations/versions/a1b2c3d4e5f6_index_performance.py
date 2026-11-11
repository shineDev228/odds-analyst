"""index de performance pour le calendrier et le journal

Revision ID: a1b2c3d4e5f6
Revises: f2a7c9d4e613
Create Date: 2026-11-10 21:00:00.000000

Migration strictement additive : deux index composites accélèrent les lectures
fréquentes sans modifier aucune donnée.

- `matches (season_id, kickoff_at)` : liste d'une saison triée par date.
- `sync_runs (created_at)` : journal lu du plus récent au plus ancien.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f2a7c9d4e613"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_matches_season_kickoff", "matches", ["season_id", "kickoff_at"], unique=False
    )
    op.create_index("ix_sync_runs_created_at", "sync_runs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sync_runs_created_at", table_name="sync_runs")
    op.drop_index("ix_matches_season_kickoff", table_name="matches")
