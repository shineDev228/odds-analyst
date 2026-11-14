"""Instantanés quotidiens : équipes, classements et board marché.

Ces tables ne nourrissent pas le moteur. Elles constituent l'historique que le
fournisseur ne conserve pas : une valeur non capturée un jour donné est perdue
définitivement sur le plan gratuit.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.match import Match
    from app.models.reference import Competition, Season, Team


class TeamSnapshot(Base, TimestampMixin):
    """Force et fréquences d'une équipe, relevées un jour donné."""

    __tablename__ = "team_snapshots"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    elo_rating: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    elo_games_counted: Mapped[int | None] = mapped_column(Integer)
    elo_last_match_date: Mapped[date | None] = mapped_column(Date)

    matches_played: Mapped[int | None] = mapped_column(Integer)
    btts_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    over_2_5_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    goals_scored: Mapped[int | None] = mapped_column(Integer)
    goals_conceded: Mapped[int | None] = mapped_column(Integer)
    clean_sheets: Mapped[int | None] = mapped_column(Integer)
    form_string: Mapped[str | None] = mapped_column(String(10))

    home_wins: Mapped[int | None] = mapped_column(Integer)
    home_draws: Mapped[int | None] = mapped_column(Integer)
    home_losses: Mapped[int | None] = mapped_column(Integer)
    away_wins: Mapped[int | None] = mapped_column(Integer)
    away_draws: Mapped[int | None] = mapped_column(Integer)
    away_losses: Mapped[int | None] = mapped_column(Integer)

    team: Mapped["Team"] = relationship()

    __table_args__ = (
        UniqueConstraint("team_id", "captured_on", name="uq_team_snapshot_day"),
        CheckConstraint(
            "(btts_rate IS NULL OR (btts_rate >= 0 AND btts_rate <= 1))"
            " AND (over_2_5_rate IS NULL OR (over_2_5_rate >= 0 AND over_2_5_rate <= 1))",
            name="ck_team_snapshot_rates",
        ),
        CheckConstraint(
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
    )


class StandingsSnapshot(Base, TimestampMixin):
    """Position et bilan d'une équipe au classement, un jour donné."""

    __tablename__ = "standings_snapshots"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    competition_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    rank: Mapped[int | None] = mapped_column(Integer)
    played: Mapped[int | None] = mapped_column(Integer)
    wins: Mapped[int | None] = mapped_column(Integer)
    draws: Mapped[int | None] = mapped_column(Integer)
    losses: Mapped[int | None] = mapped_column(Integer)
    points: Mapped[int | None] = mapped_column(Integer)
    goals_for: Mapped[int | None] = mapped_column(Integer)
    goals_against: Mapped[int | None] = mapped_column(Integer)
    form_string: Mapped[str | None] = mapped_column(String(10))

    competition: Mapped["Competition"] = relationship()
    season: Mapped["Season"] = relationship()
    team: Mapped["Team"] = relationship()

    __table_args__ = (
        UniqueConstraint("team_id", "season_id", "captured_on", name="uq_standings_snapshot_day"),
        CheckConstraint(
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
        # Lecture d'une journée de championnat : évite un balayage complet.
        Index("ix_standings_snapshot_season_day", "season_id", "captured_on"),
    )


class MarketBoardSnapshot(Base, TimestampMixin):
    """Cotes agrégées du marché, relevées à un créneau de la journée.

    Deux créneaux coexistent pour une même rencontre : le relevé du soir ne
    remplace jamais celui du matin.
    """

    __tablename__ = "market_board_snapshots"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    match_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_match_id: Mapped[str] = mapped_column(String(100), nullable=False)
    captured_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    snapshot_slot: Mapped[str] = mapped_column(String(10), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    odds_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    books_count: Mapped[int | None] = mapped_column(Integer)
    home_decimal: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    away_decimal: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    total_line: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    over_decimal: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    under_decimal: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))

    match: Mapped["Match"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "match_id", "captured_on", "snapshot_slot", name="uq_market_board_snapshot_slot"
        ),
        CheckConstraint(
            "snapshot_slot IN ('morning', 'evening')",
            name="ck_market_board_slot",
        ),
        CheckConstraint(
            "(books_count IS NULL OR books_count >= 0)"
            " AND (home_decimal IS NULL OR home_decimal > 1)"
            " AND (away_decimal IS NULL OR away_decimal > 1)"
            " AND (total_line IS NULL OR total_line >= 0)"
            " AND (over_decimal IS NULL OR over_decimal > 1)"
            " AND (under_decimal IS NULL OR under_decimal > 1)",
            name="ck_market_board_values",
        ),
        Index("ix_market_board_snapshot_day_slot", "captured_on", "snapshot_slot"),
    )
