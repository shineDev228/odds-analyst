"""Normalisation des noms et appariement prudent des équipes et rencontres.

Deux niveaux d'appariement coexistent :

- `same_team` : égalité stricte après normalisation. Utilisé pour l'import des
  équipes, où une erreur créerait un doublon durable.
- `same_team_relaxed` : tolère les abréviations et les variantes de nom
  (`Lyon` / `Olympique Lyonnais`, `Brest` / `Stade Brestois 29`). Réservé aux
  événements de cotes, où le coup d'envoi et les deux équipes doivent
  correspondre, et où l'ambiguïté reste soumise à l'utilisateur.

Aucune fusion automatique : une association n'est retenue que si une seule
rencontre correspond, sinon l'utilisateur associe lui-même.
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
    # Marqueurs de clubs français : Entente, Association Jeunesse, Racing Club…
    "es",
    "aj",
    "rc",
    "ogc",
    "osc",
    "sco",
    "acf",
    "usl",
    "hsc",
    "csa",
    "losc",
    "estac",
)

# Mots qui désignent la structure du club, pas son identité.
_GENERIC = {
    "association",
    "athletic",
    "atletico",
    "club",
    "de",
    "des",
    "du",
    "entente",
    "football",
    "l",
    "la",
    "le",
    "les",
    "municipal",
    "olympique",
    "sport",
    "sporting",
    "sports",
    "stade",
    "union",
}

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


def _core_tokens(normalized: str) -> tuple[str, ...]:
    """Tokens porteurs d'identité : ni mot générique, ni numéro, ni sigle."""
    return tuple(
        token
        for token in normalized.split()
        if token not in _GENERIC
        and token not in _SUFFIXES
        and not token.isdigit()
        and len(token) > 1
    )


def _token_similar(left: str, right: str) -> bool:
    """Deux tokens désignent-ils le même club ? (`brest` / `brestois`)."""
    if left == right:
        return True
    short, long = sorted((left, right), key=len)
    if len(short) < 4:
        return False
    if long.startswith(short):
        return True
    prefix = 0
    for first, second in zip(short, long, strict=False):
        if first != second:
            break
        prefix += 1
    return prefix >= 4 and len(long) - len(short) <= 3


def _same_core(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    if not left or not right:
        return False
    if len(left) == len(right):
        return all(
            _token_similar(first, second) for first, second in zip(left, right, strict=True)
        )
    short, long = (left, right) if len(left) < len(right) else (right, left)
    # Un nom court ne couvre qu'une partie du nom complet, avec un seul
    # qualificatif de plus au maximum (`Bordeaux` / `Girondins de Bordeaux`).
    # Deux mots supplémentaires signalent une identité différente (`Paris` /
    # `Paris Saint-Germain`) : pas d'association automatique.
    if len(long) - len(short) > 1:
        return False
    for start in range(len(long) - len(short) + 1):
        if all(
            _token_similar(first, second)
            for first, second in zip(short, long[start : start + len(short)], strict=True)
        ):
            return True
    return False


def same_team_relaxed(
    name: str,
    short_name: str | None,
    other_name: str,
    other_short: str | None,
) -> bool:
    """Égalité stricte, ou même cœur de nom une fois les mots génériques retirés.

    Tolère les abréviations courantes (`Lyon`, `Brest`, `Rennes`) sans jamais
    fusionner deux clubs dont les noms portent des identités différentes.
    """
    if same_team(name, short_name, other_name, other_short):
        return True
    for left in _keys(name, short_name):
        for right in _keys(other_name, other_short):
            if _same_core(_core_tokens(left), _core_tokens(right)):
                return True
    return False


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
