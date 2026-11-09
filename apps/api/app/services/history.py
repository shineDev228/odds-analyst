"""Service de l'historique des combinaisons et de la performance.

Les combinaisons sont enregistrées avec un instantané complet. Leur statut est
recalculé à chaque lecture à partir des scores actuels : aucune table de
règlement séparée n'est nécessaire.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from engine.settlement import (
    CombinationSettlement,
    CombinationStatus,
    LegRule,
    LegSettlement,
    LegStatus,
    MatchResult,
    settle_combination,
    settle_leg,
    summarize_performance,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.deps import as_utc
from app.models.combination import SavedCombination, SavedCombinationLeg
from app.models.market import Market, MarketSubject, Selection
from app.models.match import Match, MatchStatus
from app.models.reference import Season
from app.models.user import User
from app.schemas.common import Page
from app.schemas.history import (
    CombinationSaveRequest,
    PerformanceSummaryRead,
    SavedCombinationRead,
    SavedLegRead,
)
from app.schemas.prediction import PredictionRead
from app.services import audit
from app.services.combinations import model_selection
from app.services.predictions import InsufficientHistoryError, build_prediction

MAX_HISTORY = 2_000

HISTORY_WARNING = (
    "Performance calculée en unités de mise (1 unité par combinaison), sans montant "
    "en argent. Un petit échantillon ne permet aucune conclusion : les résultats "
    "passés ne garantissent pas les résultats futurs."
)

LEG_STATUS_LABELS: dict[LegStatus, str] = {
    LegStatus.GAGNEE: "Gagnée",
    LegStatus.PERDUE: "Perdue",
    LegStatus.REMBOURSEE: "Remboursée",
    LegStatus.EN_ATTENTE: "En attente",
    LegStatus.INDISPONIBLE: "Indisponible",
}

COMBINATION_STATUS_LABELS: dict[CombinationStatus, str] = {
    CombinationStatus.GAGNEE: "Gagnée",
    CombinationStatus.PERDUE: "Perdue",
    CombinationStatus.REMBOURSEE: "Remboursée",
    CombinationStatus.EN_ATTENTE: "En attente",
    CombinationStatus.INDISPONIBLE: "Indisponible",
}

MARKET_FAMILIES_BY_CODE: dict[str, str] = {
    "1X2": "resultat",
    "DOUBLE_CHANCE": "double_chance",
    "PLUS_MOINS": "totaux",
}

SUPPORTED_CODES: dict[str, frozenset[str]] = {
    "resultat": frozenset({"1", "X", "2"}),
    "double_chance": frozenset({"1X", "12", "X2"}),
    "totaux": frozenset({"plus", "moins"}),
}

_COMBINATION_LOAD = (selectinload(SavedCombination.legs),)
_MATCH_LOAD = (
    selectinload(Match.home_team),
    selectinload(Match.away_team),
    selectinload(Match.season).selectinload(Season.competition),
)


class InvalidSave(ValueError):
    """La combinaison ne peut pas être enregistrée en l'état."""


class HistoryNotFound(LookupError):
    """Combinaison ou sélection introuvable."""


def _load_combination(db: Session, user_id: UUID, combination_id: UUID) -> SavedCombination:
    combination = db.scalar(
        select(SavedCombination)
        .options(*_COMBINATION_LOAD)
        .where(
            SavedCombination.id == combination_id,
            SavedCombination.user_id == user_id,
        )
        .execution_options(populate_existing=True)
    )
    if combination is None:
        raise HistoryNotFound("Combinaison enregistrée introuvable.")
    return combination


def _all_combinations(db: Session, user_id: UUID) -> list[SavedCombination]:
    return list(
        db.scalars(
            select(SavedCombination)
            .options(*_COMBINATION_LOAD)
            .where(SavedCombination.user_id == user_id)
            .order_by(SavedCombination.created_at.desc(), SavedCombination.id.desc())
            .limit(MAX_HISTORY)
            .execution_options(populate_existing=True)
        ).all()
    )


def _matches_by_id(
    db: Session, combinations: list[SavedCombination]
) -> dict[UUID, Match]:
    match_ids = {
        leg.match_id
        for combination in combinations
        for leg in combination.legs
        if leg.match_id is not None
    }
    if not match_ids:
        return {}
    rows = db.scalars(
        select(Match)
        .options(*_MATCH_LOAD)
        .where(Match.id.in_(match_ids))
        .execution_options(populate_existing=True)
    ).all()
    return {match.id: match for match in rows}


def _settle_leg(
    leg: SavedCombinationLeg, match: Match | None
) -> tuple[LegSettlement, int | None, int | None]:
    if match is None or leg.match_id is None:
        return (
            LegSettlement(
                LegStatus.INDISPONIBLE,
                "Rencontre supprimée : sélection indisponible pour le règlement.",
            ),
            None,
            None,
        )

    result = MatchResult(
        status=match.status.value,
        home_score=match.home_score,
        away_score=match.away_score,
    )
    settlement = settle_leg(
        LegRule(
            family=leg.market_family,
            period=leg.market_period,
            selection_code=leg.selection_code,
            line=leg.line,
            decimal_odds=leg.decimal_odds,
        ),
        result,
    )
    return settlement, match.home_score, match.away_score


def _to_read(
    combination: SavedCombination,
    matches: dict[UUID, Match],
) -> SavedCombinationRead:
    legs: list[SavedLegRead] = []
    for leg in combination.legs:
        settlement, home_score, away_score = _settle_leg(
            leg, matches.get(leg.match_id) if leg.match_id else None
        )
        legs.append(
            SavedLegRead(
                id=leg.id,
                position=leg.position,
                match_id=leg.match_id,
                market_id=leg.market_id,
                selection_id=leg.selection_id,
                match_label=leg.match_label,
                competition_name=leg.competition_name,
                kickoff_at=leg.kickoff_at,
                market_name=leg.market_name,
                market_family=leg.market_family,
                market_period=leg.market_period,
                selection_code=leg.selection_code,
                selection_label=leg.selection_label,
                line=leg.line,
                decimal_odds=leg.decimal_odds,
                probability=leg.probability,
                low=leg.low,
                high=leg.high,
                status=settlement.status,
                status_label=LEG_STATUS_LABELS[settlement.status],
                reason=settlement.reason,
                home_score=home_score,
                away_score=away_score,
            )
        )

    aggregate = settle_combination(
        [leg.status for leg in legs],
        [leg.decimal_odds for leg in legs],
    )
    return SavedCombinationRead(
        id=combination.id,
        created_at=as_utc(combination.created_at),
        nombre_selections=combination.nombre_selections,
        cote_min=combination.cote_min,
        cote_max=combination.cote_max,
        marches_autorises=combination.marches_autorises,
        total_odds=combination.total_odds,
        probability=combination.probability,
        low=combination.low,
        high=combination.high,
        expected_value=combination.expected_value,
        note=combination.note,
        status=aggregate.status,
        status_label=COMBINATION_STATUS_LABELS[aggregate.status],
        effective_odds=aggregate.effective_odds,
        payout_units=aggregate.payout_units,
        net_units=aggregate.net_units,
        selections=legs,
    )


def _to_reads(db: Session, combinations: list[SavedCombination]) -> list[SavedCombinationRead]:
    matches = _matches_by_id(db, combinations)
    return [_to_read(combination, matches) for combination in combinations]


def _validate_rule(market: Market, selection: Selection) -> tuple[str, str, float | None]:
    if market.subject != MarketSubject.MATCH:
        raise InvalidSave("Seuls les marchés portant sur la rencontre peuvent être enregistrés.")
    if market.period != "match":
        raise InvalidSave("Seuls les marchés de la période « match » peuvent être enregistrés.")

    family = market.family
    code = selection.code
    if code not in SUPPORTED_CODES.get(family, frozenset()):
        raise InvalidSave("Cette sélection n'est pas réglable par le modèle v1.")

    line = market.line if market.line is not None else selection.line
    if family == "totaux" and line is None:
        raise InvalidSave("Une ligne de totaux est nécessaire pour régler la sélection.")
    return family, code, line


def save_combination(
    db: Session,
    user: User,
    payload: CombinationSaveRequest,
) -> SavedCombinationRead:
    """Valide puis enregistre une combinaison générée."""
    now = datetime.now(UTC)
    allowed_families = {
        MARKET_FAMILIES_BY_CODE[code]
        for code in payload.parametres.marches_autorises
        if code in MARKET_FAMILIES_BY_CODE
    }
    unknown = set(payload.parametres.marches_autorises) - set(MARKET_FAMILIES_BY_CODE)
    if unknown:
        raise InvalidSave(f"Marché inconnu : {', '.join(sorted(unknown))}.")
    if not allowed_families:
        raise InvalidSave("Aucun marché autorisé n'est renseigné pour cette combinaison.")

    selection_ids = [item.selection_id for item in payload.selections]
    selections = {
        row.id: row
        for row in db.scalars(
            select(Selection)
            .options(
                selectinload(Selection.market),
                selectinload(Selection.snapshots),
            )
            .where(Selection.id.in_(selection_ids))
        ).all()
    }
    match_ids = [item.match_id for item in payload.selections]
    matches = {
        row.id: row
        for row in db.scalars(
            select(Match)
            .options(*_MATCH_LOAD)
            .where(Match.id.in_(match_ids))
        ).all()
    }

    predictions: dict[UUID, PredictionRead] = {}
    legs: list[SavedCombinationLeg] = []
    total_odds = 1.0
    probability = 1.0
    low = 1.0
    high = 1.0

    for position, item in enumerate(payload.selections):
        selection = selections.get(item.selection_id)
        if selection is None:
            raise InvalidSave("Sélection introuvable : régénérez la combinaison.")
        market = selection.market
        if market is None:
            raise InvalidSave("Marché introuvable pour cette sélection.")
        if market.match_id != item.match_id:
            raise InvalidSave(
                "La sélection ne correspond pas à la rencontre indiquée : régénérez la combinaison."
            )

        match = matches.get(item.match_id)
        if match is None:
            raise InvalidSave("Rencontre introuvable : régénérez la combinaison.")
        if match.status != MatchStatus.PROGRAMME or as_utc(match.kickoff_at) <= now:
            raise InvalidSave(
                f"La rencontre « {match.home_team.name} — {match.away_team.name} » "
                "n'est plus à venir : elle ne peut pas être enregistrée."
            )

        family, code, line = _validate_rule(market, selection)
        if family not in allowed_families:
            raise InvalidSave(
                "Le marché de cette sélection n'est pas autorisé par les paramètres enregistrés."
            )

        snapshot = next(
            (
                row
                for row in selection.snapshots
                if abs(row.decimal_odds - item.decimal_odds) <= 1e-9
            ),
            None,
        )
        if snapshot is None:
            raise InvalidSave(
                "La cote indiquée ne correspond à aucun relevé enregistré : "
                "régénérez la combinaison."
            )

        prediction = predictions.get(match.id)
        if prediction is None:
            try:
                prediction = build_prediction(db, match.id)
            except InsufficientHistoryError as exc:
                raise InvalidSave(
                    f"Historique insuffisant pour « {match.home_team.name} — "
                    f"{match.away_team.name} » : la combinaison ne peut pas être enregistrée."
                ) from exc
            predictions[match.id] = prediction

        mapped = model_selection(market, selection, prediction)
        if mapped is None:
            raise InvalidSave(
                "Cette sélection n'est pas couverte par le modèle v1 : "
                "elle ne peut pas être enregistrée."
            )
        _, leg_probability, leg_low, leg_high = mapped
        odds = float(snapshot.decimal_odds)

        total_odds *= odds
        probability *= leg_probability
        low *= leg_low
        high *= leg_high
        legs.append(
            SavedCombinationLeg(
                position=position,
                match_id=match.id,
                market_id=market.id,
                selection_id=selection.id,
                match_label=f"{match.home_team.name} — {match.away_team.name}",
                competition_name=match.season.competition.name,
                kickoff_at=as_utc(match.kickoff_at),
                market_name=market.name,
                market_family=family,
                market_period=market.period,
                selection_code=code,
                selection_label=selection.label,
                line=line,
                decimal_odds=odds,
                probability=leg_probability,
                low=leg_low,
                high=leg_high,
            )
        )

    if not (
        payload.parametres.cote_min - 1e-9
        <= total_odds
        <= payload.parametres.cote_max + 1e-9
    ):
        raise InvalidSave(
            "La cote totale ne correspond pas à la fourchette enregistrée : "
            "régénérez la combinaison."
        )

    fingerprint = hashlib.sha256(
        "|".join(
            sorted(
                f"{item.match_id}:{item.selection_id}:{item.decimal_odds:.10g}"
                for item in payload.selections
            )
        ).encode("utf-8")
    ).hexdigest()

    combination = SavedCombination(
        user_id=user.id,
        nombre_selections=len(legs),
        cote_min=payload.parametres.cote_min,
        cote_max=payload.parametres.cote_max,
        marches_autorises=payload.parametres.marches_autorises,
        total_odds=total_odds,
        probability=probability,
        low=min(1.0, max(0.0, low)),
        high=min(1.0, max(0.0, high)),
        expected_value=probability * total_odds - 1.0,
        fingerprint=fingerprint,
        note=payload.note,
        legs=legs,
    )
    db.add(combination)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise InvalidSave("Cette combinaison est déjà enregistrée.") from exc

    audit.record(
        db,
        "combination.save",
        user_id=user.id,
        entity="saved_combination",
        entity_id=str(combination.id),
        payload={
            "nombre_selections": combination.nombre_selections,
            "total_odds": combination.total_odds,
        },
    )

    stored = _load_combination(db, user.id, combination.id)
    return _to_read(stored, _matches_by_id(db, [stored]))


def list_combinations(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    status: str = "toutes",
) -> Page[SavedCombinationRead]:
    reads = _to_reads(db, _all_combinations(db, user.id))
    if status != "toutes":
        reads = [item for item in reads if item.status.value == status]
    total = len(reads)
    start = (page - 1) * page_size
    return Page(
        items=reads[start : start + page_size],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_combination(db: Session, user: User, combination_id: UUID) -> SavedCombinationRead:
    stored = _load_combination(db, user.id, combination_id)
    return _to_read(stored, _matches_by_id(db, [stored]))


def delete_combination(db: Session, user: User, combination_id: UUID) -> None:
    stored = _load_combination(db, user.id, combination_id)
    db.delete(stored)
    db.commit()
    audit.record(
        db,
        "combination.delete",
        user_id=user.id,
        entity="saved_combination",
        entity_id=str(combination_id),
    )


def build_performance(db: Session, user: User) -> PerformanceSummaryRead:
    reads = _to_reads(db, _all_combinations(db, user.id))
    summary = summarize_performance(
        [
            CombinationSettlement(
                status=item.status,
                effective_odds=item.effective_odds,
                payout_units=item.payout_units,
                net_units=item.net_units,
            )
            for item in reads
        ]
    )
    return PerformanceSummaryRead(
        total=summary.total,
        en_attente=summary.en_attente,
        gagnees=summary.gagnees,
        perdues=summary.perdues,
        remboursees=summary.remboursees,
        indisponibles=summary.indisponibles,
        reglees=summary.reglees,
        taux_reussite=summary.taux_reussite,
        cote_moyenne=summary.cote_moyenne,
        unites_engagees=summary.unites_engagees,
        unites_retournees=summary.unites_retournees,
        resultat_net=summary.resultat_net,
        roi=summary.roi,
        avertissement=HISTORY_WARNING,
    )


__all__ = [
    "HistoryNotFound",
    "InvalidSave",
    "build_performance",
    "delete_combination",
    "get_combination",
    "list_combinations",
    "save_combination",
]
