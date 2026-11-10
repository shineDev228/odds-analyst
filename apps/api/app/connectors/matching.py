"""Normalisation des noms et appariement prudent des équipes et rencontres.

Aucune fusion automatique : une égalité stricte suffit pour associer, tout le
reste est proposé à l'utilisateur.
"""

import difflib
import re
import unicodedata
from datetime import datetime

_SUFFIXES = (
    "afc",
    "cf",
    "fc",
    "sc",
    "ac",
    "as",
    "us",
    "sv",
    "sk",
    "fk",
    "if",
    "bk",
)
_PUNCTUATION = re.compile(r"[^a-z0-9]+")


def normalize_name(value: str) -> str:
    """Minuscules, accents retirés, ponctuation neutralisée, suffixes ignorés."""
    text = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in text if not unicodedata.combining(char))
    tokens = [token for token in _PUNCTUATION.split(ascii_text.lower()) if token]
    while tokens and tokens[-1] in _SUFFIXES:
        tokens.pop()
    while tokens and tokens[0] in _SUFFIXES:
        tokens.pop(0)
    return " ".join(tokens)


def _keys(name: str, short_name: str | None) -> set[str]:
    keys = {normalize_name(name)}
    if short_name:
        keys.add(normalize_name(short_name))
    return {key for key in keys if key}


def same_team(name: str, short_name: str | None, other_name: str, other_short: str | None) -> bool:
    """Égalité stricte d'au moins une clé normalisée."""
    return bool(_keys(name, short_name) & _keys(other_name, other_short))


def similar_teams(
    name: str, candidates: list[tuple[str, str, str | None]], *, threshold: float = 0.86
) -> list[tuple[str, float]]:
    """Suggestions triées, jamais appliquées automatiquement.

    `candidates` contient des triplets `(identifiant, nom, nom court)`.
    """
    target = normalize_name(name)
    scored: list[tuple[str, float]] = []
    for identifier, candidate_name, short_name in candidates:
        best = 0.0
        for key in _keys(candidate_name, short_name):
            best = max(best, difflib.SequenceMatcher(None, target, key).ratio())
        if best >= threshold:
            scored.append((identifier, round(best, 3)))
    return sorted(scored, key=lambda item: item[1], reverse=True)


def kickoff_close(left: datetime, right: datetime, tolerance_minutes: int = 30) -> bool:
    """Deux coups d'envoi sont considérés identiques dans la tolérance."""
    delta = abs((left - right).total_seconds())
    return delta <= tolerance_minutes * 60
