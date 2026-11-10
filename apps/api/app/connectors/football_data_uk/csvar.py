"""Lecture tolérante des fichiers CSV de football-data.co.uk.

Les fichiers sont majoritairement ASCII mais certains championnats contiennent
des accents : on tente l'UTF-8 puis on retombe sur Windows-1252. Aucune ligne ne
doit faire échouer l'import complet : les valeurs illisibles deviennent `None`.
"""

import csv
import io
from datetime import date, datetime
from typing import Any

from app.connectors.base import ProviderPayloadError

DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d")


def decode_bytes(content: bytes) -> str:
    """Décode le fichier en UTF-8, avec repli Windows-1252."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")


def read_dicts(text: str) -> list[dict[str, str]]:
    """Lit un CSV en dictionnaires, sans lignes vides ni pied de page."""
    if not text.strip():
        raise ProviderPayloadError("Le fichier CSV du fournisseur est vide.")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ProviderPayloadError("Le fichier CSV du fournisseur est illisible.")
    champs = {nom.strip() for nom in reader.fieldnames if nom}
    manquants = [nom for nom in ("Date", "HomeTeam", "AwayTeam") if nom not in champs]
    if manquants:
        raise ProviderPayloadError(
            "Colonnes manquantes dans le fichier CSV : " + ", ".join(manquants) + "."
        )
    lignes: list[dict[str, str]] = []
    for brute in reader:
        ligne = {
            (cle or "").strip(): (valeur or "").strip()
            for cle, valeur in brute.items()
            if cle is not None
        }
        if not ligne.get("Date") or not ligne.get("HomeTeam") or not ligne.get("AwayTeam"):
            continue
        lignes.append(ligne)
    return lignes


def parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    for format_ in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), format_).date()
        except ValueError:
            continue
    return None


def parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return int(float(value.strip().replace(",", ".")))
    except ValueError:
        return None


def parse_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return float(value.strip().replace(",", "."))
    except ValueError:
        return None


__all__ = [
    "DATE_FORMATS",
    "decode_bytes",
    "parse_date",
    "parse_float",
    "parse_int",
    "read_dicts",
]
