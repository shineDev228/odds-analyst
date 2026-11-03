"""Référentiel sportif : sports, compétitions, saisons, équipes."""

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Sport(Base, TimestampMixin):
    __tablename__ = "sports"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)

    competitions: Mapped[list["Competition"]] = relationship(back_populates="sport")


class Competition(Base, TimestampMixin):
    __tablename__ = "competitions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    sport_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sports.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    country: Mapped[str | None] = mapped_column(String(80))
    tier: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    sport: Mapped[Sport] = relationship(back_populates="competitions")
    seasons: Mapped[list["Season"]] = relationship(
        back_populates="competition", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("sport_id", "name", "country", name="uq_competition"),)


class Season(Base, TimestampMixin):
    __tablename__ = "seasons"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    competition_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(40), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    competition: Mapped[Competition] = relationship(back_populates="seasons")

    __table_args__ = (UniqueConstraint("competition_id", "label", name="uq_season_label"),)


class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    sport_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sports.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    short_name: Mapped[str | None] = mapped_column(String(40))
    country: Mapped[str | None] = mapped_column(String(80))

    sport: Mapped[Sport] = relationship()

    __table_args__ = (UniqueConstraint("sport_id", "name", name="uq_team_name"),)
