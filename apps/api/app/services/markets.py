"""Services des marchés : signatures, création, calculs et sérialisation."""

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from engine.odds import fair_odds, fair_probabilities, implied_probability, overround_percent
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.market import Market, MarketSubject, MarketTemplate, OddsSnapshot, Selection
from app.models.match import Match
from app.schemas.market import (
    MarketCreate,
    MarketRead,
    MarketUpdate,
    OddsCreate,
    OddsRead,
    SelectionRead,
)

MARKET_LOAD_OPTIONS = (
    selectinload(Market.selections).selectinload(Selection.snapshots),
    selectinload(Market.subject_team),
)


def as_utc(value: datetime) -> datetime:
    """SQLite renvoie des dates naïves ; PostgreSQL des dates avec fuseau."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def slugify(value: str) -> str:
    """Code stable et lisible dérivé d'un libellé."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    code = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_text).strip("_").lower()
    return code or "selection"


def build_signature(
    *,
    template_code: str | None,
    name: str,
    family: str,
    period: str,
    subject: MarketSubject,
    subject_team_id: UUID | None,
    subject_player: str | None,
    line: float | None,
    line2: float | None,
) -> str:
    """Empreinte d'identité d'un marché au sein d'une rencontre.

    Deux marchés de même code, période, sujet et ligne sont considérés comme des
    doublons, même si leur libellé diffère légèrement.
    """
    player = (subject_player or "").strip().lower()
    parts = [
        template_code or "",
        name.strip().lower(),
        family.strip().lower(),
        period.strip().lower(),
        str(subject),
        str(subject_team_id or ""),
        player,
        "" if line is None else f"{line:.4f}",
        "" if line2 is None else f"{line2:.4f}",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def load_market(db: Session, market_id: UUID) -> Market | None:
    return db.scalar(
        select(Market)
        .options(*MARKET_LOAD_OPTIONS)
        .where(Market.id == market_id)
        .execution_options(populate_existing=True)
    )


def load_match_markets(db: Session, match_id: UUID) -> list[Market]:
    return list(
        db.scalars(
            select(Market)
            .options(*MARKET_LOAD_OPTIONS)
            .where(Market.match_id == match_id)
            .order_by(Market.family, Market.name, Market.created_at)
            .execution_options(populate_existing=True)
        ).all()
    )


def _latest_snapshot(selection: Selection) -> OddsSnapshot | None:
    if not selection.snapshots:
        return None
    return max(selection.snapshots, key=lambda item: (as_utc(item.captured_at), str(item.id)))


def to_selection_read(
    selection: Selection, fair: dict[UUID, tuple[float, float]] | None
) -> SelectionRead:
    latest = _latest_snapshot(selection)
    probability = implied_probability(latest.decimal_odds) if latest else None
    fair_probability = fair[selection.id][0] if fair and selection.id in fair else None
    adjusted_odds = fair[selection.id][1] if fair and selection.id in fair else None
    return SelectionRead(
        id=selection.id,
        market_id=selection.market_id,
        code=selection.code,
        label=selection.label,
        line=selection.line,
        sort_order=selection.sort_order,
        latest_odds=latest.decimal_odds if latest else None,
        latest_captured_at=latest.captured_at if latest else None,
        implied_probability=probability,
        fair_probability=fair_probability,
        fair_odds=adjusted_odds,
        odds_count=len(selection.snapshots),
        history=[
            OddsRead.model_validate(snapshot)
            for snapshot in sorted(
                selection.snapshots,
                key=lambda item: (as_utc(item.captured_at), str(item.id)),
                reverse=True,
            )
        ],
    )


def to_market_read(market: Market) -> MarketRead:
    latest_values = [
        latest.decimal_odds
        for selection in market.selections
        if (latest := _latest_snapshot(selection)) is not None
    ]
    complete = bool(market.selections) and len(latest_values) == len(market.selections)

    fair: dict[UUID, tuple[float, float]] | None = None
    margin: float | None = None
    implied_total: float | None = None
    if complete:
        probabilities = fair_probabilities(latest_values)
        adjusted = fair_odds(latest_values)
        fair = {
            selection.id: (probability, odds)
            for selection, probability, odds in zip(
                market.selections, probabilities, adjusted, strict=True
            )
        }
        margin = overround_percent(latest_values)
        implied_total = sum(1 / value for value in latest_values)

    latest_dates = [
        as_utc(latest.captured_at)
        for selection in market.selections
        if (latest := _latest_snapshot(selection)) is not None
    ]
    return MarketRead(
        id=market.id,
        match_id=market.match_id,
        template_code=market.template_code,
        name=market.name,
        family=market.family,
        period=market.period,
        subject=market.subject,
        subject_team_id=market.subject_team_id,
        subject_team_name=market.subject_team.name if market.subject_team else None,
        subject_player=market.subject_player,
        line=market.line,
        line2=market.line2,
        is_custom=market.is_custom,
        notes=market.notes,
        created_at=market.created_at,
        latest_captured_at=max(latest_dates) if latest_dates else None,
        overround_percent=margin,
        implied_probability_total=implied_total,
        is_complete=complete,
        selections=[to_selection_read(selection, fair) for selection in market.selections],
    )


def resolve_template(db: Session, code: str | None) -> MarketTemplate | None:
    if not code:
        return None
    return db.scalar(select(MarketTemplate).where(MarketTemplate.code == code))


def _selection_specs(
    payload: MarketCreate, template: MarketTemplate | None
) -> list[dict[str, Any]]:
    provided = payload.selections or []
    if provided:
        return [item.model_dump() for item in provided]
    if template is not None:
        return [dict(item) for item in template.selection_templates]
    return []


def create_market(db: Session, match: Match, payload: MarketCreate) -> Market:
    template = resolve_template(db, payload.template_code)
    if payload.template_code and template is None:
        raise LookupError("Modèle de marché introuvable dans le catalogue.")

    explicit = payload.model_fields_set
    name = payload.name or (template.name if template else None)
    family = payload.family or (template.family if template else None)
    if not name or not family:
        raise ValueError("Le nom et la famille du marché sont obligatoires.")

    period = payload.period
    if template is not None and "period" not in explicit:
        period = template.period

    subject = payload.subject
    if template is not None and "subject" not in explicit:
        subject = template.subject

    specs = _selection_specs(payload, template)
    if len(specs) < 1:
        raise ValueError("Un marché doit comporter au moins une sélection.")

    used_codes: set[str] = set()
    rows: list[Selection] = []
    snapshots: list[tuple[int, OddsCreate]] = []
    captured_at = payload.captured_at or datetime.now(UTC)

    for index, spec in enumerate(specs):
        label = str(spec.get("label") or "").strip()
        if not label:
            raise ValueError("Chaque sélection doit avoir un libellé.")
        code = str(spec.get("code") or slugify(label))
        base_code = code
        suffix = 2
        while code in used_codes:
            code = f"{base_code}_{suffix}"
            suffix += 1
        used_codes.add(code)

        selection = Selection(
            code=code,
            label=label,
            line=spec.get("line"),
            sort_order=index,
        )
        rows.append(selection)
        odds = spec.get("decimal_odds")
        if odds is not None:
            snapshots.append(
                (
                    index,
                    OddsCreate(
                        decimal_odds=float(odds),
                        captured_at=captured_at,
                        bookmaker=payload.bookmaker,
                        source=payload.source,
                    ),
                )
            )

    signature = build_signature(
        template_code=payload.template_code,
        name=name,
        family=family,
        period=period,
        subject=subject,
        subject_team_id=payload.subject_team_id,
        subject_player=payload.subject_player,
        line=payload.line,
        line2=payload.line2,
    )

    market = Market(
        match_id=match.id,
        template_code=payload.template_code,
        name=name,
        family=family,
        period=period,
        subject=subject,
        subject_team_id=payload.subject_team_id,
        subject_player=payload.subject_player,
        line=payload.line,
        line2=payload.line2,
        signature=signature,
        is_custom=payload.template_code is None,
        notes=payload.notes,
        selections=rows,
    )
    db.add(market)
    db.flush()

    for index, odds in snapshots:
        db.add(
            OddsSnapshot(
                selection_id=rows[index].id,
                decimal_odds=odds.decimal_odds,
                captured_at=odds.captured_at or captured_at,
                bookmaker=odds.bookmaker,
                source=odds.source,
            )
        )

    db.commit()
    created = load_market(db, market.id)
    if created is None:  # pragma: no cover - défense en profondeur
        raise LookupError("Marché introuvable après création.")
    return created


def update_market(db: Session, market: Market, payload: MarketUpdate) -> Market:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(market, field, value)
    market.signature = build_signature(
        template_code=market.template_code,
        name=market.name,
        family=market.family,
        period=market.period,
        subject=market.subject,
        subject_team_id=market.subject_team_id,
        subject_player=market.subject_player,
        line=market.line,
        line2=market.line2,
    )
    db.commit()
    updated = load_market(db, market.id)
    if updated is None:  # pragma: no cover - défense en profondeur
        raise LookupError("Marché introuvable après mise à jour.")
    return updated


def add_odds(
    db: Session, market: Market, selection_id: UUID, payload: OddsCreate
) -> tuple[Selection, OddsSnapshot]:
    selection = next((item for item in market.selections if item.id == selection_id), None)
    if selection is None:
        raise LookupError("Sélection introuvable pour ce marché.")
    snapshot = OddsSnapshot(
        selection_id=selection.id,
        decimal_odds=payload.decimal_odds,
        captured_at=payload.captured_at or datetime.now(UTC),
        bookmaker=payload.bookmaker,
        source=payload.source,
        note=payload.note,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return selection, snapshot


def find_snapshot(market: Market, selection_id: UUID, snapshot_id: UUID) -> OddsSnapshot:
    selection = next((item for item in market.selections if item.id == selection_id), None)
    if selection is None:
        raise LookupError("Sélection introuvable pour ce marché.")
    snapshot = next((item for item in selection.snapshots if item.id == snapshot_id), None)
    if snapshot is None:
        raise LookupError("Relevé de cote introuvable.")
    return snapshot


def market_history(market: Market) -> list[OddsRead]:
    rows = [
        OddsRead.model_validate(snapshot)
        for selection in market.selections
        for snapshot in selection.snapshots
    ]
    return sorted(rows, key=lambda item: (as_utc(item.captured_at), str(item.id)), reverse=True)
