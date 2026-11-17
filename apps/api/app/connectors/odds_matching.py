"""Appariement des événements de cotes aux rencontres, par clé composite.

La clé est **(compétition, coup d'envoi ± 15 minutes)**, départagée par un score
de nom, avec une marge minimale entre le premier et le deuxième candidat. Le nom
seul ne suffit jamais : deux clubs dont les noms se ressemblent mais dont
l'identité diffère (`Manchester City` / `Manchester United`) sont refusés.

En cas de doute, aucune décision n'est prise : l'événement est signalé comme
ambigu et rien n'est écrit. Un repli par le nom, à ± 7 jours, couvre les
rencontres reportées ; il est marqué `name_fallback`, jamais silencieux.

Ce module est pur : il ne lit ni la base ni le réseau.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from uuid import UUID

from app.connectors.matching import (
    identity_tokens,
    normalize_name,
    same_identity,
    same_team,
    same_team_relaxed,
)

KICKOFF_TOLERANCE_MINUTES = 15
FALLBACK_DAYS = 7
MIN_CONFIDENCE = 0.60
MIN_MARGIN = 0.10
# Un score de nom plafonné sous le seuil : les deux clubs n'ont pas la même
# identité, même si leurs libellés se ressemblent.
DISTINCT_IDENTITY_CAP = 0.55


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    """Rencontre interne candidate, avec les noms du fournisseur de faits."""

    match_id: UUID
    home_name: str
    away_name: str
    kickoff_at: datetime


@dataclass(frozen=True, slots=True)
class EventRef:
    """Événement de cotes réduit à ce qui sert à la décision."""

    event_id: str
    home_name: str
    away_name: str
    commence_at: datetime


@dataclass(frozen=True, slots=True)
class Decision:
    """Résultat d'une décision : rattachement, ambiguïté ou absence de candidat."""

    match_id: UUID | None = None
    method: str | None = None
    confidence: float = 0.0
    margin: float = 0.0
    reason: str = "unmatched"

    @property
    def matched(self) -> bool:
        return self.match_id is not None


def _utc(value: datetime) -> datetime:
    """SQLite renvoie des dates naïves ; tout est comparé en UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _minutes_apart(left: datetime, right: datetime) -> float:
    return abs((_utc(left) - _utc(right)).total_seconds()) / 60.0


def team_confidence(event_name: str, candidate_name: str) -> float:
    """Score de 0 à 1 entre un nom du marché et un nom interne.

    - égalité stricte après normalisation : 1,0 ;
    - appariement souple connu (`Lyon` / `Olympique Lyonnais`) : 0,9 ;
    - sinon similarité des libellés, plafonnée si les identités diffèrent.
    """
    if same_team(event_name, None, candidate_name, None):
        return 1.0
    if same_team_relaxed(event_name, None, candidate_name, None):
        return 0.9

    left = normalize_name(event_name)
    right = normalize_name(candidate_name)
    if not left or not right:
        return 0.0
    ratio = SequenceMatcher(None, left, right).ratio()

    left_tokens = identity_tokens(event_name)
    right_tokens = identity_tokens(candidate_name)
    if left_tokens and right_tokens and not same_identity(event_name, candidate_name):
        return min(ratio, DISTINCT_IDENTITY_CAP)
    return ratio


def pair_confidence(event: EventRef, candidate: MatchCandidate) -> float:
    """Le maillon faible des deux équipes : garantit le sens domicile/extérieur."""
    home = team_confidence(event.home_name, candidate.home_name)
    away = team_confidence(event.away_name, candidate.away_name)
    return min(home, away)


def decide_event(
    event: EventRef,
    candidates: list[MatchCandidate],
    *,
    tolerance_minutes: int = KICKOFF_TOLERANCE_MINUTES,
    fallback_days: int = FALLBACK_DAYS,
) -> Decision:
    """Décide du rattachement d'un événement, sans jamais deviner."""
    window = [
        (pair_confidence(event, candidate), candidate)
        for candidate in candidates
        if _minutes_apart(event.commence_at, candidate.kickoff_at) <= tolerance_minutes
    ]
    if window:
        window.sort(key=lambda item: (item[0], str(item[1].match_id)), reverse=True)
        best_confidence, best = window[0]
        margin = (
            round(best_confidence - window[1][0], 3) if len(window) > 1 else 1.0
        )
        if best_confidence >= MIN_CONFIDENCE and margin >= MIN_MARGIN:
            return Decision(
                match_id=best.match_id,
                method="kickoff",
                confidence=round(best_confidence, 3),
                margin=margin,
                reason="matched",
            )
        if best_confidence >= MIN_CONFIDENCE:
            return Decision(
                confidence=round(best_confidence, 3),
                margin=margin,
                reason="ambiguous",
            )

    horizon = timedelta(days=fallback_days)
    fallback = [
        (pair_confidence(event, candidate), candidate)
        for candidate in candidates
        if abs(_utc(event.commence_at) - _utc(candidate.kickoff_at)) <= horizon
        and same_team_relaxed(event.home_name, None, candidate.home_name, None)
        and same_team_relaxed(event.away_name, None, candidate.away_name, None)
    ]
    if fallback:
        fallback.sort(key=lambda item: (item[0], str(item[1].match_id)), reverse=True)
        best_confidence, best = fallback[0]
        margin = round(best_confidence - fallback[1][0], 3) if len(fallback) > 1 else 1.0
        if margin < MIN_MARGIN:
            return Decision(
                confidence=round(best_confidence, 3),
                margin=margin,
                reason="ambiguous",
            )
        return Decision(
            match_id=best.match_id,
            method="name_fallback",
            confidence=round(best_confidence, 3),
            margin=margin,
            reason="matched",
        )

    return Decision(reason="unmatched")
