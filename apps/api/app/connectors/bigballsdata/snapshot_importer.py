"""Écriture des snapshots d'équipe : une ligne par équipe et par jour.

Règles :

- la contrainte ``UNIQUE (team_id, captured_on)`` interdit tout doublon ;
- une ligne déjà présente est mise à jour sur place ;
- une valeur connue n'est **jamais** effacée par un ``NULL`` fournisseur ;
- ``captured_at`` suit l'heure réelle de la dernière capture, sans compter
  comme un changement de valeur.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.bigballsdata.snapshot_mapping import (
    NormalizedMarketBoard,
    NormalizedTeamSnapshot,
)
from app.models.match import Match
from app.models.reference import Team
from app.models.snapshot import MarketBoardSnapshot, TeamSnapshot

SNAPSHOT_COLUMNS = (
    "source_as_of",
    "elo_rating",
    "elo_games_counted",
    "elo_last_match_date",
    "matches_played",
    "btts_rate",
    "over_2_5_rate",
    "goals_scored",
    "goals_conceded",
    "clean_sheets",
    "form_string",
    "home_wins",
    "home_draws",
    "home_losses",
    "away_wins",
    "away_draws",
    "away_losses",
)


def upsert_team_snapshot(
    db: Session, *, team: Team, snapshot: NormalizedTeamSnapshot
) -> str:
    """Crée ou met à jour la ligne du jour ; retourne ``created``, ``updated``
    ou ``unchanged``."""
    row = db.scalar(
        select(TeamSnapshot).where(
            TeamSnapshot.team_id == team.id,
            TeamSnapshot.captured_on == snapshot.captured_on,
        )
    )
    values = {column: getattr(snapshot, column) for column in SNAPSHOT_COLUMNS}
    if row is None:
        db.add(
            TeamSnapshot(
                team_id=team.id,
                captured_on=snapshot.captured_on,
                captured_at=snapshot.captured_at,
                **values,
            )
        )
        db.flush()
        return "created"

    changed = False
    for field, value in values.items():
        # Un champ absent chez le fournisseur ne doit pas effacer une valeur
        # déjà connue : la ligne du jour reste la plus complète possible.
        if value is None:
            continue
        if _same_value(getattr(row, field), value):
            continue
        setattr(row, field, value)
        changed = True
    row.captured_at = snapshot.captured_at
    db.flush()
    return "updated" if changed else "unchanged"


def _same_value(current: object, value: object) -> bool:
    if isinstance(current, datetime) and isinstance(value, datetime):
        left = current if current.tzinfo else current.replace(tzinfo=UTC)
        right = value if value.tzinfo else value.replace(tzinfo=UTC)
        return left.astimezone(UTC) == right.astimezone(UTC)
    if isinstance(current, Decimal) and isinstance(value, Decimal):
        return current == value
    return current == value


BOARD_COLUMNS = (
    "external_match_id",
    "odds_updated_at",
    "books_count",
    "home_decimal",
    "away_decimal",
    "total_line",
    "over_decimal",
    "under_decimal",
)


def upsert_board_snapshot(
    db: Session, *, match: Match, snapshot: NormalizedMarketBoard
) -> str:
    """Crée ou met à jour le relevé d'un créneau, sans doublon.

    Le matin et le soir coexistent : la contrainte d'unicité porte sur
    ``(match_id, captured_on, snapshot_slot)``. Un rejeu du même créneau met à
    jour la ligne existante, sans jamais effacer une cote connue par ``NULL``.
    """
    row = db.scalar(
        select(MarketBoardSnapshot).where(
            MarketBoardSnapshot.match_id == match.id,
            MarketBoardSnapshot.captured_on == snapshot.captured_on,
            MarketBoardSnapshot.snapshot_slot == snapshot.snapshot_slot,
        )
    )
    values = {column: getattr(snapshot, column) for column in BOARD_COLUMNS}
    if row is None:
        db.add(
            MarketBoardSnapshot(
                match_id=match.id,
                captured_on=snapshot.captured_on,
                snapshot_slot=snapshot.snapshot_slot,
                captured_at=snapshot.captured_at,
                **values,
            )
        )
        db.flush()
        return "created"

    changed = False
    for field, value in values.items():
        if value is None:
            continue
        if _same_value(getattr(row, field), value):
            continue
        setattr(row, field, value)
        changed = True
    row.captured_at = snapshot.captured_at
    db.flush()
    return "updated" if changed else "unchanged"


__all__ = [
    "BOARD_COLUMNS",
    "SNAPSHOT_COLUMNS",
    "upsert_board_snapshot",
    "upsert_team_snapshot",
]
