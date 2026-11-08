"""Marchés, sélections et relevés de cotes.

Le modèle est volontairement universel : un marché est décrit par une famille,
une période, un sujet (match, équipe ou joueur), une ou deux lignes et une liste
de sélections. Il couvre aussi bien le 1X2 que le score exact, les corners, les
cartons ou les marchés joueurs, pour tous les sports.
"""

import enum
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin

if TYPE_CHECKING:
    from app.models.match import Match
    from app.models.reference import Team


class MarketSubject(enum.StrEnum):
    MATCH = "match"
    TEAM = "team"
    PLAYER = "player"


class MarketTemplate(Base, TimestampMixin):
    """Modèle de marché du catalogue (1xBet et générique)."""

    __tablename__ = "market_templates"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    sport_code: Mapped[str | None] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    family: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(40), nullable=False, default="match")
    subject: Mapped[MarketSubject] = mapped_column(
        Enum(
            MarketSubject,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
            name="market_subject",
        ),
        default=MarketSubject.MATCH,
        nullable=False,
    )
    line_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="aucune")
    selection_templates: Mapped[list[dict]] = mapped_column(JSONType, nullable=False, default=list)
    description: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "line_kind IN ('aucune', 'simple', 'double', 'intervalle', 'libre')",
            name="ck_market_template_line_kind",
        ),
    )


class Market(Base, TimestampMixin):
    """Marché saisi pour une rencontre donnée."""

    __tablename__ = "markets"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    match_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_code: Mapped[str | None] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    family: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(40), nullable=False, default="match")
    subject: Mapped[MarketSubject] = mapped_column(
        Enum(
            MarketSubject,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
            name="market_subject",
        ),
        default=MarketSubject.MATCH,
        nullable=False,
    )
    subject_team_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("teams.id", ondelete="RESTRICT"), index=True
    )
    subject_player: Mapped[str | None] = mapped_column(String(120))
    line: Mapped[float | None] = mapped_column(Float)
    line2: Mapped[float | None] = mapped_column(Float)
    signature: Mapped[str] = mapped_column(String(64), nullable=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000))

    match: Mapped["Match"] = relationship(back_populates="markets")
    subject_team: Mapped["Team | None"] = relationship()
    selections: Mapped[list["Selection"]] = relationship(
        back_populates="market", cascade="all, delete-orphan", order_by="Selection.sort_order"
    )

    __table_args__ = (UniqueConstraint("match_id", "signature", name="uq_market_match_signature"),)


class Selection(Base, TimestampMixin):
    """Issue d'un marché (1, X, 2, Plus, Moins, Oui, Non, score exact…)."""

    __tablename__ = "selections"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    market_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("markets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    line: Mapped[float | None] = mapped_column(Float)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    market: Mapped[Market] = relationship(back_populates="selections")
    snapshots: Mapped[list["OddsSnapshot"]] = relationship(
        back_populates="selection",
        cascade="all, delete-orphan",
        order_by="OddsSnapshot.captured_at.desc()",
    )

    __table_args__ = (UniqueConstraint("market_id", "code", name="uq_selection_market_code"),)


class OddsSnapshot(Base):
    """Relevé de cote horodaté — jamais écrasé (historique append-only)."""

    __tablename__ = "odds_snapshots"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    selection_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("selections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decimal_odds: Mapped[float] = mapped_column(Float, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    bookmaker: Mapped[str] = mapped_column(String(80), nullable=False, default="1xBet")
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="manuel")
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    selection: Mapped[Selection] = relationship(back_populates="snapshots")

    __table_args__ = (
        CheckConstraint("decimal_odds > 1", name="ck_odds_decimal_gt_one"),
        Index("ix_odds_selection_captured", "selection_id", "captured_at"),
    )
