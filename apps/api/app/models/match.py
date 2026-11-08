"""Rencontres et statistiques d'équipe par match."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin

if TYPE_CHECKING:
    from app.models.market import Market
    from app.models.reference import Season, Team


class MatchStatus(enum.StrEnum):
    PROGRAMME = "programme"
    EN_COURS = "en_cours"
    TERMINE = "termine"
    REPORTE = "reporte"
    ANNULE = "annule"


class Match(Base, TimestampMixin):
    __tablename__ = "matches"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    season_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    home_team_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    away_team_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kickoff_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[MatchStatus] = mapped_column(
        Enum(
            MatchStatus,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
            name="match_status",
        ),
        default=MatchStatus.PROGRAMME,
        nullable=False,
        index=True,
    )
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    half_time_home_score: Mapped[int | None] = mapped_column(Integer)
    half_time_away_score: Mapped[int | None] = mapped_column(Integer)
    venue: Mapped[str | None] = mapped_column(String(120))
    referee: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(String(2000))

    season: Mapped["Season"] = relationship()
    home_team: Mapped["Team"] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped["Team"] = relationship(foreign_keys=[away_team_id])
    stats: Mapped[list["TeamMatchStats"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    markets: Mapped[list["Market"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("home_team_id <> away_team_id", name="ck_match_distinct_teams"),
        CheckConstraint(
            "(home_score IS NULL AND away_score IS NULL) OR (home_score >= 0 AND away_score >= 0)",
            name="ck_match_scores_positive",
        ),
    )


class TeamMatchStats(Base, TimestampMixin):
    __tablename__ = "team_match_stats"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    match_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)

    goals_for: Mapped[int | None] = mapped_column(Integer)
    goals_against: Mapped[int | None] = mapped_column(Integer)
    shots: Mapped[int | None] = mapped_column(Integer)
    shots_on_target: Mapped[int | None] = mapped_column(Integer)
    possession: Mapped[float | None] = mapped_column(Float)
    corners: Mapped[int | None] = mapped_column(Integer)
    yellow_cards: Mapped[int | None] = mapped_column(Integer)
    red_cards: Mapped[int | None] = mapped_column(Integer)
    expected_goals: Mapped[float | None] = mapped_column(Float)
    extra: Mapped[dict | None] = mapped_column(JSONType)

    match: Mapped[Match] = relationship(back_populates="stats")
    team: Mapped["Team"] = relationship()

    __table_args__ = (
        UniqueConstraint("match_id", "team_id", name="uq_stats_match_team"),
        CheckConstraint(
            "possession IS NULL OR (possession >= 0 AND possession <= 100)",
            name="ck_stats_possession",
        ),
    )
