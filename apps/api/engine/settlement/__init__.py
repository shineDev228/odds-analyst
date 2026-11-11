"""Règlement pur des sélections et des combinaisons.

Le module ne connaît ni la base de données ni FastAPI. Il reçoit la règle
enregistrée avec la sélection et l'état actuel de la rencontre, puis renvoie un
statut explicable. La performance est exprimée en unités de mise : une
combinaison réglée compte pour une unité, sans montant en argent.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import prod
from statistics import mean

SUPPORTED_FAMILIES: dict[str, frozenset[str]] = {
    "resultat": frozenset({"1", "X", "2"}),
    "double_chance": frozenset({"1X", "12", "X2"}),
    "totaux": frozenset({"plus", "moins"}),
    "btts": frozenset({"oui", "non"}),
}

PENDING_MATCH_STATUSES = frozenset({"programme", "en_cours"})
VOID_MATCH_STATUSES = frozenset({"reporte", "annule"})


class LegStatus(StrEnum):
    GAGNEE = "gagnee"
    PERDUE = "perdue"
    REMBOURSEE = "remboursee"
    EN_ATTENTE = "en_attente"
    INDISPONIBLE = "indisponible"


class CombinationStatus(StrEnum):
    GAGNEE = "gagnee"
    PERDUE = "perdue"
    REMBOURSEE = "remboursee"
    EN_ATTENTE = "en_attente"
    INDISPONIBLE = "indisponible"


@dataclass(frozen=True)
class LegRule:
    """Règle de règlement figée avec la sélection enregistrée."""

    family: str
    period: str
    selection_code: str
    line: float | None
    decimal_odds: float

    def __post_init__(self) -> None:
        if self.decimal_odds <= 1:
            raise ValueError("Une cote décimale doit être strictement supérieure à 1.")


@dataclass(frozen=True)
class MatchResult:
    """État minimal d'une rencontre nécessaire au règlement."""

    status: str
    home_score: int | None = None
    away_score: int | None = None


@dataclass(frozen=True)
class LegSettlement:
    status: LegStatus
    reason: str


@dataclass(frozen=True)
class CombinationSettlement:
    """Résultat d'une combinaison, exprimé pour une unité de mise."""

    status: CombinationStatus
    effective_odds: float
    payout_units: float | None
    net_units: float | None


@dataclass(frozen=True)
class PerformanceSummary:
    total: int
    en_attente: int
    gagnees: int
    perdues: int
    remboursees: int
    indisponibles: int
    reglees: int
    taux_reussite: float | None
    cote_moyenne: float | None
    unites_engagees: float
    unites_retournees: float
    resultat_net: float
    roi: float | None


def _score_label(result: MatchResult) -> str:
    return f"{result.home_score}-{result.away_score}"


def _result_code(result: MatchResult) -> str:
    if result.home_score is None or result.away_score is None:  # pragma: no cover - défense
        raise ValueError("Score manquant.")
    if result.home_score > result.away_score:
        return "1"
    if result.home_score == result.away_score:
        return "X"
    return "2"


def _settle_1x2(rule: LegRule, result: MatchResult) -> LegSettlement:
    actual = _result_code(result)
    label = _score_label(result)
    if rule.selection_code == actual:
        return LegSettlement(LegStatus.GAGNEE, f"Score {label} : sélection gagnante.")
    return LegSettlement(LegStatus.PERDUE, f"Score {label} : sélection perdante.")


def _settle_double_chance(rule: LegRule, result: MatchResult) -> LegSettlement:
    actual = _result_code(result)
    combinations = {
        "1X": {"1", "X"},
        "12": {"1", "2"},
        "X2": {"X", "2"},
    }
    label = _score_label(result)
    if actual in combinations.get(rule.selection_code, set()):
        return LegSettlement(LegStatus.GAGNEE, f"Score {label} : sélection gagnante.")
    return LegSettlement(LegStatus.PERDUE, f"Score {label} : sélection perdante.")


def _settle_total(rule: LegRule, result: MatchResult) -> LegSettlement:
    if rule.line is None:
        return LegSettlement(
            LegStatus.INDISPONIBLE,
            "Ligne absente : sélection indisponible pour le règlement.",
        )
    if result.home_score is None or result.away_score is None:  # pragma: no cover - défense
        return LegSettlement(LegStatus.INDISPONIBLE, "Score manquant : sélection indisponible.")

    total = result.home_score + result.away_score
    line_label = f"{rule.line:g}".replace(".", ",")
    if abs(total - rule.line) <= 1e-9:
        return LegSettlement(
            LegStatus.REMBOURSEE,
            f"Total de {total} buts : la ligne {line_label} est atteinte "
            "exactement, sélection remboursée.",
        )

    won = (rule.selection_code == "plus" and total > rule.line) or (
        rule.selection_code == "moins" and total < rule.line
    )
    if won:
        return LegSettlement(
            LegStatus.GAGNEE,
            f"Total de {total} buts contre la ligne {line_label} : sélection gagnante.",
        )
    return LegSettlement(
        LegStatus.PERDUE,
        f"Total de {total} buts contre la ligne {line_label} : sélection perdante.",
    )


def _settle_btts(rule: LegRule, result: MatchResult) -> LegSettlement:
    """Règle « les deux équipes marquent » : aucun remboursement possible."""
    if result.home_score is None or result.away_score is None:  # pragma: no cover - défense
        return LegSettlement(LegStatus.INDISPONIBLE, "Score manquant : sélection indisponible.")

    both_scored = result.home_score > 0 and result.away_score > 0
    label = _score_label(result)
    won = (rule.selection_code == "oui" and both_scored) or (
        rule.selection_code == "non" and not both_scored
    )
    if won:
        return LegSettlement(LegStatus.GAGNEE, f"Score {label} : sélection gagnante.")
    return LegSettlement(LegStatus.PERDUE, f"Score {label} : sélection perdante.")


def settle_leg(rule: LegRule, result: MatchResult) -> LegSettlement:
    """Règle une sélection à partir de son instantané et de la rencontre actuelle."""
    if result.status in VOID_MATCH_STATUSES:
        return LegSettlement(
            LegStatus.REMBOURSEE,
            "Rencontre reportée ou annulée : sélection remboursée.",
        )
    if result.status in PENDING_MATCH_STATUSES:
        return LegSettlement(LegStatus.EN_ATTENTE, "Rencontre pas encore terminée.")
    if result.status != "termine":
        return LegSettlement(
            LegStatus.INDISPONIBLE,
            "Statut de rencontre inconnu : sélection indisponible.",
        )
    if result.home_score is None or result.away_score is None:
        return LegSettlement(
            LegStatus.INDISPONIBLE,
            "Rencontre terminée sans score : sélection indisponible.",
        )
    if rule.period != "match":
        return LegSettlement(
            LegStatus.INDISPONIBLE,
            "Marché hors période « match » : non réglable par le modèle statistique.",
        )

    if rule.family == "resultat" and rule.selection_code in SUPPORTED_FAMILIES["resultat"]:
        return _settle_1x2(rule, result)
    if (
        rule.family == "double_chance"
        and rule.selection_code in SUPPORTED_FAMILIES["double_chance"]
    ):
        return _settle_double_chance(rule, result)
    if rule.family == "totaux" and rule.selection_code in SUPPORTED_FAMILIES["totaux"]:
        return _settle_total(rule, result)
    if rule.family == "btts" and rule.selection_code in SUPPORTED_FAMILIES["btts"]:
        return _settle_btts(rule, result)

    return LegSettlement(
        LegStatus.INDISPONIBLE,
        "Marché non réglable par le modèle statistique : sélection indisponible.",
    )


def settle_combination(
    leg_statuses: Sequence[LegStatus],
    leg_odds: Sequence[float],
) -> CombinationSettlement:
    """Agrège les statuts des jambes en un statut de combinaison."""
    if not leg_statuses or len(leg_statuses) != len(leg_odds):
        raise ValueError("Une combinaison doit comporter au moins une jambe cohérente.")
    if any(odds <= 1 for odds in leg_odds):
        raise ValueError("Une cote décimale doit être strictement supérieure à 1.")

    statuses = tuple(leg_statuses)
    effective_odds = prod(
        odds
        for odds, status in zip(leg_odds, statuses, strict=True)
        if status != LegStatus.REMBOURSEE
    )
    effective_odds = effective_odds if effective_odds > 1 else 1.0

    if LegStatus.PERDUE in statuses:
        return CombinationSettlement(
            status=CombinationStatus.PERDUE,
            effective_odds=effective_odds,
            payout_units=0.0,
            net_units=-1.0,
        )
    if LegStatus.INDISPONIBLE in statuses:
        return CombinationSettlement(
            status=CombinationStatus.INDISPONIBLE,
            effective_odds=effective_odds,
            payout_units=None,
            net_units=None,
        )
    if LegStatus.EN_ATTENTE in statuses:
        return CombinationSettlement(
            status=CombinationStatus.EN_ATTENTE,
            effective_odds=effective_odds,
            payout_units=None,
            net_units=None,
        )
    if all(status == LegStatus.REMBOURSEE for status in statuses):
        return CombinationSettlement(
            status=CombinationStatus.REMBOURSEE,
            effective_odds=1.0,
            payout_units=1.0,
            net_units=0.0,
        )

    return CombinationSettlement(
        status=CombinationStatus.GAGNEE,
        effective_odds=effective_odds,
        payout_units=effective_odds,
        net_units=effective_odds - 1.0,
    )


def summarize_performance(
    settlements: Sequence[CombinationSettlement],
) -> PerformanceSummary:
    """Calcule la synthèse en unités sur les combinaisons fournies."""
    statuses = [item.status for item in settlements]
    won = statuses.count(CombinationStatus.GAGNEE)
    lost = statuses.count(CombinationStatus.PERDUE)
    refunded = statuses.count(CombinationStatus.REMBOURSEE)
    pending = statuses.count(CombinationStatus.EN_ATTENTE)
    unavailable = statuses.count(CombinationStatus.INDISPONIBLE)
    settled = won + lost + refunded
    decided = won + lost

    staked = float(settled)
    returned = sum(
        item.payout_units or 0.0
        for item in settlements
        if item.status
        in {
            CombinationStatus.GAGNEE,
            CombinationStatus.PERDUE,
            CombinationStatus.REMBOURSEE,
        }
    )
    net = returned - staked
    settled_odds = [
        item.effective_odds
        for item in settlements
        if item.status
        in {
            CombinationStatus.GAGNEE,
            CombinationStatus.PERDUE,
            CombinationStatus.REMBOURSEE,
        }
    ]

    return PerformanceSummary(
        total=len(settlements),
        en_attente=pending,
        gagnees=won,
        perdues=lost,
        remboursees=refunded,
        indisponibles=unavailable,
        reglees=settled,
        taux_reussite=(won / decided) if decided else None,
        cote_moyenne=mean(settled_odds) if settled_odds else None,
        unites_engagees=staked,
        unites_retournees=returned,
        resultat_net=net,
        roi=(net / staked) if staked > 0 else None,
    )


__all__ = [
    "SUPPORTED_FAMILIES",
    "CombinationSettlement",
    "CombinationStatus",
    "LegRule",
    "LegSettlement",
    "LegStatus",
    "MatchResult",
    "PerformanceSummary",
    "settle_combination",
    "settle_leg",
    "summarize_performance",
]
