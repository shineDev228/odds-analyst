"""Appariement des lignes CSV aux rencontres, par clé de résultat.

La rencontre est identifiée par **(compétition, date exacte, score final, score
à la mi-temps)**. Le nom ne sert jamais à trouver la rencontre : il confirme
seulement le **sens domicile/extérieur**, et départage les rares rencontres qui
partagent le même résultat le même jour.

Règles, dans l'ordre :

* aucun candidat sur le résultat → rien n'est écrit ;
* un seul candidat → il est retenu, même si son nom est un exonyme
  (`Paris SG` / `Paris Saint-Germain`, mesuré à 0,55) : le résultat désigne
  déjà la rencontre. Un sens manifestement inversé reste refusé ;
* plusieurs candidats → le nom doit départager, avec un seuil de 0,60 et une
  marge de 0,25. En cas de doute, rien n'est écrit.

Un xG manquant ne coûte rien ; un xG attribué à la mauvaise rencontre fausserait
le moteur et la crédibilité de l'application.

Ce module est pur : il ne lit ni la base ni le réseau.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.connectors.football_data_uk.mapping import CsvRow
from app.connectors.odds_matching import team_confidence

# En dessous de ce score de nom, le sens domicile/extérieur n'est pas confirmé.
MIN_CONFIDENCE = 0.60
# Deux candidats à moins de 0,25 l'un de l'autre : on demande au lieu de deviner.
MIN_MARGIN = 0.25


@dataclass(frozen=True, slots=True)
class CsvCandidate:
    """Rencontre interne candidate, réduite à ce qui sert à la décision."""

    match_id: UUID
    played_on: date
    home_name: str
    away_name: str
    home_score: int | None
    away_score: int | None
    half_time_home: int | None
    half_time_away: int | None


@dataclass(frozen=True, slots=True)
class CsvDecision:
    """Résultat d'une décision : ligne appliquée, en attente ou sans rencontre."""

    match_id: UUID | None = None
    confidence: float = 0.0
    margin: float = 0.0
    # matched | ambiguous | unmatched
    reason: str = "unmatched"
    note: str | None = None

    @property
    def matched(self) -> bool:
        return self.match_id is not None

    @property
    def pending(self) -> bool:
        """Une décision non tranchée est enregistrée mais n'écrit rien."""
        return not self.matched


def _same_result(row: CsvRow, candidate: CsvCandidate) -> bool:
    """Date, score final et mi-temps : la clé de la rencontre."""
    if candidate.played_on != row.played_on:
        return False
    if candidate.home_score != row.home_score:
        return False
    if candidate.away_score != row.away_score:
        return False
    # Une mi-temps inconnue d'un côté ne disqualifie pas : elle ne peut pas
    # contredire. Deux mi-temps connues et différentes, si.
    if (
        row.half_time_home is not None
        and row.half_time_away is not None
        and candidate.half_time_home is not None
        and candidate.half_time_away is not None
    ):
        return (candidate.half_time_home, candidate.half_time_away) == (
            row.half_time_home,
            row.half_time_away,
        )
    return True


def _orientations(row: CsvRow, candidate: CsvCandidate) -> tuple[float, float]:
    """Confiance dans les deux sens : (direct, inversé)."""
    direct = min(
        team_confidence(row.home_name, candidate.home_name),
        team_confidence(row.away_name, candidate.away_name),
    )
    inversee = min(
        team_confidence(row.home_name, candidate.away_name),
        team_confidence(row.away_name, candidate.home_name),
    )
    return direct, inversee


def orientation_confidence(row: CsvRow, candidate: CsvCandidate) -> float:
    """Confiance dans le sens domicile/extérieur, de 0 à 1.

    Le maillon faible des deux équipes impose la décision : si l'une des deux
    est inversée, la ligne est refusée. Un candidat dont les noms vont mieux
    dans l'autre sens vaut zéro, jamais « presque ».
    """
    direct, inversee = _orientations(row, candidate)
    if inversee > direct:
        return 0.0
    return direct


def decide_row(
    row: CsvRow,
    candidates: list[CsvCandidate],
    *,
    min_confidence: float = MIN_CONFIDENCE,
    min_margin: float = MIN_MARGIN,
) -> CsvDecision:
    """Décide du rattachement d'une ligne CSV, sans jamais deviner.

    Trois cas :

    * **aucun** candidat sur le résultat → rien n'est écrit ;
    * **un seul** candidat → il est retenu : le résultat (date, score final,
      mi-temps) désigne déjà la rencontre, et le nom ne peut pas disqualifier
      un exonyme (`Paris SG` / `Paris Saint-Germain`). Seul un sens
      manifestement inversé est refusé ;
    * **plusieurs** candidats → le nom doit les départager, avec le seuil et la
      marge habituels. En cas de doute, rien n'est écrit.
    """
    scored = [
        (orientation_confidence(row, candidate), candidate)
        for candidate in candidates
        if _same_result(row, candidate)
    ]
    if not scored:
        return CsvDecision(note="Aucune rencontre terminée sur ce score à cette date.")

    scored.sort(key=lambda item: (item[0], str(item[1].match_id)), reverse=True)
    best_confidence, best = scored[0]

    if len(scored) == 1:
        direct, inversee = _orientations(row, best)
        if inversee > direct:
            return CsvDecision(
                confidence=0.0,
                margin=1.0,
                reason="unmatched",
                note=(
                    "Seule rencontre sur ce résultat, mais les noms vont mieux dans "
                    "l'autre sens : aucune écriture."
                ),
            )
        note = None
        if best_confidence < min_confidence:
            note = (
                "Seule rencontre sur ce résultat ; nom différent (exonyme probable). "
                "Le rattachement reste fondé sur le résultat, pas sur le nom."
            )
        return CsvDecision(
            match_id=best.match_id,
            confidence=round(best_confidence, 3),
            margin=1.0,
            reason="matched",
            note=note,
        )

    margin = round(best_confidence - scored[1][0], 3)
    if best_confidence >= min_confidence and margin >= min_margin:
        return CsvDecision(
            match_id=best.match_id,
            confidence=round(best_confidence, 3),
            margin=margin,
            reason="matched",
        )
    if best_confidence >= min_confidence:
        return CsvDecision(
            confidence=round(best_confidence, 3),
            margin=margin,
            reason="ambiguous",
            note=(
                "Deux rencontres correspondent au même score : marge insuffisante, "
                "aucune écriture."
            ),
        )
    return CsvDecision(
        confidence=round(best_confidence, 3),
        margin=margin,
        reason="unmatched",
        note="Noms trop différents : le sens domicile/extérieur n'est pas confirmé.",
    )


__all__ = [
    "MIN_CONFIDENCE",
    "MIN_MARGIN",
    "CsvCandidate",
    "CsvDecision",
    "decide_row",
    "orientation_confidence",
]
