"""fournisseur csv football-data.co.uk

Revision ID: f2a7c9d4e613
Revises: d8e1f3a5b7c9
Create Date: 2026-11-10 10:00:00.000000

Migration additive : la contrainte de fournisseur accepte une valeur de plus.
Aucune donnée existante n'est réécrite.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f2a7c9d4e613"
down_revision: str | None = "d8e1f3a5b7c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONTRAINTE = "ck_connector_link_provider"
ANCIENS = "'bigballsdata', 'the_odds_api', 'football_data'"
NOUVEAUX = ANCIENS + ", 'football_data_uk'"


def upgrade() -> None:
    op.drop_constraint(CONTRAINTE, "connector_links", type_="check")
    op.create_check_constraint(CONTRAINTE, "connector_links", f"provider IN ({NOUVEAUX})")


def downgrade() -> None:
    op.drop_constraint(CONTRAINTE, "connector_links", type_="check")
    op.create_check_constraint(CONTRAINTE, "connector_links", f"provider IN ({ANCIENS})")
