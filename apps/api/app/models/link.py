"""Liens bornés vers les sources périphériques : lignes CSV et marché.

Ces tables ne créent jamais d'entité. Elles rattachent une ligne de fichier ou
un événement de cotes à une rencontre **déjà connue**, en conservant la méthode
et la confiance de la décision. Une ligne douteuse reste en attente et n'écrit
rien : un xG manquant ne coûte rien, un xG faux coûterait la crédibilité du
moteur.
"""

from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.match import Match
    from app.models.reference import Season


class CsvLink(Base, TimestampMixin):
    """Rattachement d'une ligne CSV (xG et cotes de clôture) à une rencontre.

    La clé naturelle est ``(source, row_key)`` : une ligne de fichier ne peut
    être appliquée qu'une fois. Une rencontre ne peut recevoir qu'une seule
    ligne appliquée (index partiel sur ``match_id`` quand ``status =
    'applied'``). En cas de doute, ``status`` vaut ``'pending'`` et
    ``match_id`` reste nul : rien n'est écrit.
    """

    __tablename__ = "csv_links"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(
        String(40), default="football_data_uk", server_default="football_data_uk", nullable=False
    )
    season_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Empreinte de la ligne : division, date, score final, mi-temps et noms
    # normalisés. Le résultat seul ne suffit pas : deux rencontres peuvent se
    # terminer sur le même score le même jour.
    row_key: Mapped[str] = mapped_column(String(200), nullable=False)
    row_date: Mapped[date] = mapped_column(Date, nullable=False)
    home_team_name: Mapped[str] = mapped_column(String(120), nullable=False)
    away_team_name: Mapped[str] = mapped_column(String(120), nullable=False)
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    half_time_home_score: Mapped[int | None] = mapped_column(Integer)
    half_time_away_score: Mapped[int | None] = mapped_column(Integer)
    match_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("matches.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", nullable=False, index=True
    )
    method: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[float | None] = mapped_column(Numeric(precision=4, scale=3))
    margin: Mapped[float | None] = mapped_column(Numeric(precision=4, scale=3))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(String(500))

    season: Mapped["Season"] = relationship()
    match: Mapped["Match | None"] = relationship()

    __table_args__ = (
        UniqueConstraint("source", "row_key", name="uq_csv_link_row"),
        CheckConstraint(
            "status IN ('applied', 'pending', 'ignored')",
            name="ck_csv_link_status",
        ),
        CheckConstraint(
            "method IS NULL OR method IN ('score', 'name', 'manual')",
            name="ck_csv_link_method",
        ),
        CheckConstraint(
            "(confidence IS NULL OR (confidence >= 0 AND confidence <= 1))"
            " AND (margin IS NULL OR (margin >= 0 AND margin <= 1))",
            name="ck_csv_link_scores",
        ),
        CheckConstraint(
            "(home_score IS NULL OR home_score >= 0)"
            " AND (away_score IS NULL OR away_score >= 0)"
            " AND (half_time_home_score IS NULL OR half_time_home_score >= 0)"
            " AND (half_time_away_score IS NULL OR half_time_away_score >= 0)",
            name="ck_csv_link_goals_positive",
        ),
        CheckConstraint(
            "status <> 'applied' OR match_id IS NOT NULL",
            name="ck_csv_link_applied_has_match",
        ),
        # Une rencontre ne peut recevoir qu'une seule ligne CSV appliquée.
        Index(
            "uq_csv_link_applied_match",
            "match_id",
            unique=True,
            postgresql_where=text("status = 'applied'"),
            sqlite_where=text("status = 'applied'"),
        ),
    )


class OddsEventLink(Base, TimestampMixin):
    """Rattachement d'un événement de cotes à une rencontre.

    Clé composite à l'import : (compétition, coup d'envoi ± 15 min), départagée
    par le nom, avec une marge minimale. Une décision enregistrée n'est jamais
    reposée. Une rencontre n'a qu'un seul lien actif à la fois : un événement
    reporté désactive l'ancien lien au lieu d'en créer un second.
    """

    __tablename__ = "odds_event_links"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(
        String(40), default="the_odds_api", server_default="the_odds_api", nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    match_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Code de compétition du fournisseur de faits (ex. « ligue1 »).
    competition_code: Mapped[str] = mapped_column(String(40), nullable=False)
    commence_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    home_team_name: Mapped[str] = mapped_column(String(120), nullable=False)
    away_team_name: Mapped[str] = mapped_column(String(120), nullable=False)
    method: Mapped[str] = mapped_column(
        String(20), default="kickoff", server_default="kickoff", nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Numeric(precision=4, scale=3))
    margin: Mapped[float | None] = mapped_column(Numeric(precision=4, scale=3))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(String(500))

    match: Mapped["Match"] = relationship()

    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_odds_event_link_event"),
        CheckConstraint(
            "method IN ('kickoff', 'name_fallback', 'manual')",
            name="ck_odds_event_link_method",
        ),
        CheckConstraint(
            "(confidence IS NULL OR (confidence >= 0 AND confidence <= 1))"
            " AND (margin IS NULL OR (margin >= 0 AND margin <= 1))",
            name="ck_odds_event_link_scores",
        ),
        # Un seul lien actif par rencontre.
        Index(
            "uq_odds_event_link_active_match",
            "match_id",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
    )
