"""Combinaisons enregistrées et instantanés de leurs sélections.

Une combinaison sauvegardée ne dépend pas de l'état futur des marchés : chaque
jambe conserve la rencontre, le marché, la sélection, la cote et les estimations
au moment de l'enregistrement. Le statut est recalculé à la lecture.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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
    from app.models.market import Market, Selection
    from app.models.match import Match
    from app.models.user import User


class SavedCombination(Base, TimestampMixin):
    """Combinaison générée puis enregistrée par l'utilisateur."""

    __tablename__ = "saved_combinations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nombre_selections: Mapped[int] = mapped_column(Integer, nullable=False)
    cote_min: Mapped[float] = mapped_column(Float, nullable=False)
    cote_max: Mapped[float] = mapped_column(Float, nullable=False)
    marches_autorises: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    total_odds: Mapped[float] = mapped_column(Float, nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    expected_value: Mapped[float] = mapped_column(Float, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))

    user: Mapped["User"] = relationship()
    legs: Mapped[list["SavedCombinationLeg"]] = relationship(
        back_populates="combination",
        cascade="all, delete-orphan",
        order_by="SavedCombinationLeg.position",
    )

    __table_args__ = (
        CheckConstraint(
            "nombre_selections BETWEEN 2 AND 15",
            name="ck_saved_combination_nombre_selections",
        ),
        CheckConstraint(
            "cote_min > 1 AND cote_max > cote_min",
            name="ck_saved_combination_odds_range",
        ),
        CheckConstraint("total_odds > 1", name="ck_saved_combination_total_odds"),
        CheckConstraint(
            "probability >= 0 AND probability <= 1",
            name="ck_saved_combination_probability",
        ),
        CheckConstraint(
            "low >= 0 AND high <= 1 AND low <= probability AND probability <= high",
            name="ck_saved_combination_interval",
        ),
        UniqueConstraint(
            "user_id",
            "fingerprint",
            name="uq_saved_combination_user_fingerprint",
        ),
    )


class SavedCombinationLeg(Base, TimestampMixin):
    """Sélection figée au moment de l'enregistrement d'une combinaison."""

    __tablename__ = "saved_combination_legs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    combination_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("saved_combinations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    match_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("matches.id", ondelete="SET NULL"), index=True
    )
    market_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("markets.id", ondelete="SET NULL"), index=True
    )
    selection_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("selections.id", ondelete="SET NULL"), index=True
    )
    match_label: Mapped[str] = mapped_column(String(240), nullable=False)
    competition_name: Mapped[str] = mapped_column(String(160), nullable=False)
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    market_name: Mapped[str] = mapped_column(String(160), nullable=False)
    market_family: Mapped[str] = mapped_column(String(80), nullable=False)
    market_period: Mapped[str] = mapped_column(String(40), nullable=False)
    selection_code: Mapped[str] = mapped_column(String(80), nullable=False)
    selection_label: Mapped[str] = mapped_column(String(120), nullable=False)
    line: Mapped[float | None] = mapped_column(Float)
    decimal_odds: Mapped[float] = mapped_column(Float, nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)

    combination: Mapped[SavedCombination] = relationship(back_populates="legs")
    match: Mapped["Match | None"] = relationship()
    market: Mapped["Market | None"] = relationship()
    selection: Mapped["Selection | None"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "combination_id",
            "position",
            name="uq_saved_combination_leg_position",
        ),
        UniqueConstraint(
            "combination_id",
            "match_id",
            name="uq_saved_combination_leg_match",
        ),
        CheckConstraint("position >= 0", name="ck_saved_combination_leg_position"),
        CheckConstraint(
            "decimal_odds > 1",
            name="ck_saved_combination_leg_decimal_odds",
        ),
        CheckConstraint(
            "probability >= 0 AND probability <= 1",
            name="ck_saved_combination_leg_probability",
        ),
    )
