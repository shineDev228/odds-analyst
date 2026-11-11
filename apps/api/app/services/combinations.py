"""Service du générateur de combinaisons.

Le service charge les rencontres à venir, calcule les prédictions disponibles
et transmet des candidats au moteur pur. Aucune combinaison n'est persistée.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from engine.combos.generator import (
    CombinationCandidate,
    CombinationSearch,
    generate_combinations,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import as_utc
from app.models.market import Market, MarketSubject, Selection
from app.models.match import Match, MatchStatus
from app.models.reference import Competition, Season, Sport
from app.schemas.combination import (
    CombinationParameters,
    CombinationRead,
    CombinationRequest,
    CombinationResponse,
    CombinationSelectionRead,
)
from app.schemas.prediction import PredictionRead, PredictionSelection
from app.services.markets import latest_snapshot
from app.services.predictions import (
    AVERTISSEMENT as PREDICTION_WARNING,
)
from app.services.predictions import build_predictions
from app.services.preferences import get_preferences

MAX_MATCHES = 50

MARKET_FAMILIES: dict[str, tuple[str, ...]] = {
    "1X2": ("resultat",),
    "DOUBLE_CHANCE": ("double_chance",),
    "PLUS_MOINS": ("totaux",),
}

COMBINATION_WARNING = (
    "Combinaisons générées à partir des probabilités estimées et des cotes saisies. "
    "Aucune combinaison n'est certaine et aucune n'est un conseil de pari. "
    "Une espérance négative signifie que la marge du bookmaker reste défavorable."
)

_LOAD = (
    selectinload(Match.home_team),
    selectinload(Match.away_team),
    selectinload(Match.season).selectinload(Season.competition).selectinload(Competition.sport),
    selectinload(Match.markets).selectinload(Market.selections).selectinload(Selection.snapshots),
)


class InvalidCombinationRequest(ValueError):
    """Paramètres incohérents après fusion avec les préférences."""


def _fr(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _allowed_families(markets: Sequence[str]) -> set[str]:
    return {family for code in markets for family in MARKET_FAMILIES.get(code, ())}


def _market_is_eligible(market: Market, families: set[str]) -> bool:
    return (
        market.period == "match"
        and market.family in families
        and market.subject == MarketSubject.MATCH
    )


def model_selection(
    market: Market,
    selection: Selection,
    prediction: PredictionRead,
) -> tuple[str, float, float, float] | None:
    """Associe une sélection saisie à une probabilité du modèle statistique."""
    code = selection.code

    if market.family == "resultat" and market.period == "match" and code in {"1", "X", "2"}:
        item = next((entry for entry in prediction.resultat if entry.code == code), None)
        if item is not None:
            return f"1x2:{code}", item.probability, item.low, item.high

    if market.family == "double_chance" and market.period == "match" and code in {"1X", "12", "X2"}:
        item = next((entry for entry in prediction.double_chance if entry.code == code), None)
        if item is not None:
            return f"double_chance:{code}", item.probability, item.low, item.high

    if market.family == "totaux" and market.period == "match" and code in {"plus", "moins"}:
        line = market.line if market.line is not None else selection.line
        if line is None:
            return None
        total = next(
            (entry for entry in prediction.totaux if abs(entry.line - line) <= 1e-6),
            None,
        )
        if total is None:
            return None
        total_selection: PredictionSelection = total.over if code == "plus" else total.under
        return (
            f"total:{line:g}:{code}",
            total_selection.probability,
            total_selection.low,
            total_selection.high,
        )
    return None


def _upcoming_matches(db: Session, now: datetime) -> list[Match]:
    return list(
        db.scalars(
            select(Match)
            .join(Season, Match.season_id == Season.id)
            .join(Competition, Season.competition_id == Competition.id)
            .join(Sport, Competition.sport_id == Sport.id)
            .options(*_LOAD)
            .where(
                Sport.code == "football",
                Match.status == MatchStatus.PROGRAMME,
                Match.kickoff_at >= now,
            )
            .order_by(Match.kickoff_at.asc())
            .limit(MAX_MATCHES)
            .execution_options(populate_existing=True)
        ).all()
    )


def _candidates_for_match(
    match: Match,
    prediction: PredictionRead,
    families: set[str],
) -> list[CombinationCandidate]:
    """Construit et déduplique les candidats d'une rencontre."""
    best: dict[str, tuple[datetime, CombinationCandidate]] = {}

    for market in match.markets:
        if not _market_is_eligible(market, families):
            continue
        for selection in market.selections:
            snapshot = latest_snapshot(selection)
            if snapshot is None:
                continue
            mapped = model_selection(market, selection, prediction)
            if mapped is None:
                continue
            model_key, probability, low, high = mapped
            key = f"{match.id}:{model_key}"
            candidate = CombinationCandidate(
                key=key,
                match_id=str(match.id),
                match_label=f"{match.home_team.name} — {match.away_team.name}",
                competition_name=match.season.competition.name,
                kickoff_at=as_utc(match.kickoff_at),
                market_name=market.name,
                selection_label=selection.label,
                decimal_odds=float(snapshot.decimal_odds),
                probability=probability,
                low=low,
                high=high,
                market_id=str(market.id),
                selection_id=str(selection.id),
            )
            captured_at = as_utc(snapshot.captured_at)
            existing = best.get(key)
            if existing is None or (captured_at, candidate.decimal_odds) > (
                existing[0],
                existing[1].decimal_odds,
            ):
                best[key] = (captured_at, candidate)

    return [item[1] for item in best.values()]


def _empty_response(
    parameters: CombinationParameters,
    message: str,
    *,
    matchs_examines: int = 0,
    matchs_disponibles: int = 0,
    selections_disponibles: int = 0,
) -> CombinationResponse:
    return CombinationResponse(
        combinaisons=[],
        parametres=parameters,
        matchs_examines=matchs_examines,
        matchs_disponibles=matchs_disponibles,
        matchs_ignores=max(0, matchs_examines - matchs_disponibles),
        selections_disponibles=selections_disponibles,
        recherche_tronquee=False,
        message=message,
        avertissement=COMBINATION_WARNING,
    )


def build_combinations(
    db: Session,
    payload: CombinationRequest,
) -> CombinationResponse:
    """Génère les combinaisons à partir des préférences et de la requête."""
    preferences = get_preferences(db)
    nombre = payload.nombre_selections or preferences.nb_selections_defaut
    cote_min = payload.cote_min if payload.cote_min is not None else preferences.cote_min
    cote_max = payload.cote_max if payload.cote_max is not None else preferences.cote_max
    marches = (
        payload.marches_autorises
        if payload.marches_autorises is not None
        else preferences.marches_autorises
    )

    parameters = CombinationParameters(
        nombre_selections=nombre,
        cote_min=cote_min,
        cote_max=cote_max,
        marches_autorises=marches,
        limite=payload.limite,
    )

    if cote_max <= cote_min:
        raise InvalidCombinationRequest("La cote maximale doit être supérieure à la cote minimale.")
    if not marches:
        return _empty_response(
            parameters,
            "Aucun marché autorisé : activez au moins un marché dans les préférences "
            "ou dans le formulaire.",
        )

    families = _allowed_families(marches)
    matches = _upcoming_matches(db, datetime.now(UTC))

    # Les rencontres sans cote récente sont écartées avant tout calcul : elles ne
    # produiraient aucun candidat. Les pronostics restants partagent ensuite un
    # seul chargement d'historique.
    with_odds: list[Match] = []
    for match in matches:
        eligible = [market for market in match.markets if _market_is_eligible(market, families)]
        if any(
            latest_snapshot(selection) is not None
            for market in eligible
            for selection in market.selections
        ):
            with_odds.append(match)

    predictions = build_predictions(db, with_odds, preferences)
    groups: list[list[CombinationCandidate]] = []
    ignored = 0

    for match in matches:
        prediction = predictions.get(match.id)
        if prediction is None:
            ignored += 1
            continue

        candidates = _candidates_for_match(match, prediction, families)
        if candidates:
            groups.append(candidates)
        else:
            ignored += 1

    search: CombinationSearch = generate_combinations(
        groups,
        selections_count=nombre,
        min_odds=cote_min,
        max_odds=cote_max,
        limit=payload.limite,
    )

    if not matches:
        message = "Aucune rencontre à venir n'est enregistrée."
    elif not groups:
        message = (
            "Aucune rencontre à venir ne réunit une cote récente et un historique "
            "suffisant pour le modèle statistique."
        )
    elif len(groups) < nombre:
        message = (
            f"{len(groups)} rencontre(s) exploitable(s) pour {nombre} sélections "
            "demandées : réduisez le nombre de sélections ou ajoutez des cotes."
        )
    elif not search.combinations:
        message = (
            f"Aucune combinaison de {nombre} sélections ne tombe entre "
            f"{_fr(cote_min)} et {_fr(cote_max)}. Élargissez la fourchette ou "
            "modifiez le nombre de sélections."
        )
    else:
        message = f"{len(search.combinations)} combinaison(s) trouvée(s)."

    combinaisons = [
        CombinationRead(
            selections=[
                CombinationSelectionRead(
                    match_id=UUID(selection.match_id),
                    market_id=UUID(selection.market_id),
                    selection_id=UUID(selection.selection_id),
                    match_label=selection.match_label,
                    competition_name=selection.competition_name,
                    kickoff_at=selection.kickoff_at,
                    market_name=selection.market_name,
                    selection_label=selection.selection_label,
                    decimal_odds=selection.decimal_odds,
                    probability=selection.probability,
                    low=selection.low,
                    high=selection.high,
                )
                for selection in combination.selections
            ],
            total_odds=combination.total_odds,
            probability=combination.probability,
            low=combination.low,
            high=combination.high,
            expected_value=combination.expected_value,
        )
        for combination in search.combinations
    ]

    return CombinationResponse(
        combinaisons=combinaisons,
        parametres=parameters,
        matchs_examines=len(matches),
        matchs_disponibles=len(groups),
        matchs_ignores=ignored,
        selections_disponibles=sum(len(group) for group in groups),
        recherche_tronquee=search.truncated,
        message=message,
        avertissement=f"{COMBINATION_WARNING} {PREDICTION_WARNING}",
    )


__all__ = ["InvalidCombinationRequest", "build_combinations"]
