"""Alias des équipes entre football-data.co.uk et les noms complets.

Le fichier CSV utilise des noms courts (« Paris SG », « Lens ») alors que les
sources de calendrier utilisent les noms complets (« Paris Saint-Germain FC »).
Cette table n'associe rien automatiquement : elle propose un nom canonique, et
l'appariement final reste une égalité stricte de jetons normalisés. Une équipe
inconnue est signalée à l'utilisateur, jamais créée.
"""

from app.connectors.matching import normalize_name

_RAW: dict[str, str] = {
    # Ligue 1
    "Angers": "Angers SCO",
    "Auxerre": "AJ Auxerre",
    "Brest": "Stade Brestois 29",
    "Le Havre": "Le Havre AC",
    "Le Mans": "Le Mans FC",
    "Lens": "RC Lens",
    "Lille": "LOSC Lille",
    "Lorient": "FC Lorient",
    "Lyon": "Olympique Lyonnais",
    "Marseille": "Olympique de Marseille",
    "Monaco": "AS Monaco FC",
    "Nice": "OGC Nice",
    "Paris FC": "Paris FC",
    "Paris SG": "Paris Saint-Germain FC",
    "Rennes": "Stade Rennais FC 1901",
    "Strasbourg": "RC Strasbourg Alsace",
    "Toulouse": "Toulouse FC",
    "Troyes": "ES Troyes AC",
    # Clubs passés récemment par la Ligue 1
    "Metz": "FC Metz",
    "Nantes": "FC Nantes",
    "St Etienne": "AS Saint-Étienne",
    "Reims": "Stade de Reims",
    "Clermont": "Clermont Foot 63",
    "Montpellier": "Montpellier HSC",
}

ALIASES: dict[str, str] = {
    normalize_name(source): cible for source, cible in _RAW.items()
}


def canonical_name(raw_name: str) -> str:
    """Nom complet proposé pour un nom court du CSV (ou le nom d'origine)."""
    return ALIASES.get(normalize_name(raw_name), raw_name)


def team_key(raw_name: str) -> str:
    """Identifiant externe stable et lisible pour une équipe du fichier."""
    jeton = "-".join(normalize_name(raw_name).split())
    return jeton or "equipe"


__all__ = ["ALIASES", "canonical_name", "team_key"]
