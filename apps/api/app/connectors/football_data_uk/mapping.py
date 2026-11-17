"""Catalogue des divisions et mapping des lignes CSV vers des objets normalisés.

Le fichier ne contient ni identifiant de rencontre ni fuseau horaire : la date
est la seule référence fiable, l'heure locale n'est jamais utilisée.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from app.connectors.base import ProviderNotCoveredError, ProviderPayloadError
from app.connectors.football_data_uk.csvar import (
    parse_date,
    parse_float,
    parse_int,
    read_dicts,
)
from app.connectors.matching import normalize_name

BASE_URL = "https://football-data.co.uk"
ALLOWED_HOSTS = {"football-data.co.uk", "www.football-data.co.uk"}

DIVISIONS: dict[str, dict[str, str]] = {
    "F1": {"name": "Ligue 1", "country": "France"},
    "F2": {"name": "Ligue 2", "country": "France"},
    "E0": {"name": "Premier League", "country": "Angleterre"},
    "E1": {"name": "Championship", "country": "Angleterre"},
    "SP1": {"name": "La Liga", "country": "Espagne"},
    "SP2": {"name": "Segunda División", "country": "Espagne"},
    "I1": {"name": "Serie A", "country": "Italie"},
    "I2": {"name": "Serie B", "country": "Italie"},
    "D1": {"name": "Bundesliga", "country": "Allemagne"},
    "D2": {"name": "2. Bundesliga", "country": "Allemagne"},
    "N1": {"name": "Eredivisie", "country": "Pays-Bas"},
    "B1": {"name": "Pro League", "country": "Belgique"},
    "P1": {"name": "Primeira Liga", "country": "Portugal"},
    "T1": {"name": "Süper Lig", "country": "Turquie"},
    "G1": {"name": "Super League", "country": "Grèce"},
    "SC0": {"name": "Scottish Premiership", "country": "Écosse"},
}

_DIVISION_PATTERN = re.compile(r"^[A-Za-z0-9]{1,5}$")


def season_code(season: str) -> str:
    """Convertit `2026` ou `2026-2027` en code d'URL `2627`."""
    chiffres = re.findall(r"\d{4}", season or "")
    if not chiffres:
        raise ProviderNotCoveredError(
            "Saison externe invalide : indiquez l'année de début, par exemple 2026."
        )
    debut = int(chiffres[0])
    if not 1990 <= debut <= 2100:
        raise ProviderNotCoveredError(
            "Saison externe hors limites : indiquez une année entre 1990 et 2100."
        )
    return f"{debut % 100:02d}{(debut + 1) % 100:02d}"


def build_url(base_url: str, division: str, season: str) -> str:
    """Construit l'URL du fichier CSV, ou accepte une URL complète fournie."""
    code = (division or "").strip()
    if code.lower().startswith(("http://", "https://")):
        parsed = urlsplit(code)
        if parsed.scheme != "https" or (parsed.hostname or "") not in ALLOWED_HOSTS:
            raise ProviderNotCoveredError(
                "Seules les adresses https de football-data.co.uk sont acceptées "
                "pour ce connecteur."
            )
        return code
    if not _DIVISION_PATTERN.match(code):
        raise ProviderNotCoveredError(
            "Code de division invalide. Exemples : F1 (Ligue 1), F2 (Ligue 2), E0 (Premier League)."
        )
    racine = (base_url or BASE_URL).rstrip("/")
    return f"{racine}/mmz4281/{season_code(season)}/{code.upper()}.csv"


def division_label(division: str) -> str:
    code = (division or "").upper()
    fiche = DIVISIONS.get(code)
    return f"{fiche['name']} ({code})" if fiche else code


@dataclass(slots=True)
class CsvTeamStats:
    """Statistiques d'une équipe telles que publiées par football-data.co.uk."""

    is_home: bool
    goals_for: int
    goals_against: int
    shots: int | None = None
    shots_on_target: int | None = None
    corners: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    expected_goals: float | None = None
    fouls: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_home": self.is_home,
            "goals_for": self.goals_for,
            "goals_against": self.goals_against,
            "shots": self.shots,
            "shots_on_target": self.shots_on_target,
            "possession": None,
            "corners": self.corners,
            "yellow_cards": self.yellow_cards,
            "red_cards": self.red_cards,
            "expected_goals": self.expected_goals,
            "extra": {"fouls": self.fouls} if self.fouls is not None else None,
        }


@dataclass(slots=True)
class ClosingOdds:
    """Cotes de clôture moyennes du marché, telles que publiées dans le fichier.

    Le fichier contient plusieurs bookmakers ; on ne retient que la **moyenne**
    (`AvgCH`, `AvgCD`, `AvgCA`, `AvgC>2.5`, `AvgC<2.5`). Aucune cote n'est
    reconstruite : si une valeur manque, la cote correspondante est absente.
    """

    home: float
    draw: float
    away: float
    over_2_5: float | None = None
    under_2_5: float | None = None

    @property
    def result_1x2(self) -> dict[str, float]:
        return {"1": self.home, "X": self.draw, "2": self.away}

    @property
    def total_2_5(self) -> dict[str, float] | None:
        if self.over_2_5 is None or self.under_2_5 is None:
            return None
        return {"plus": self.over_2_5, "moins": self.under_2_5}


@dataclass(slots=True)
class CsvRow:
    """Une rencontre terminée, prête à être rapprochée du calendrier interne."""

    division: str
    played_on: date
    kickoff: str | None
    home_name: str
    away_name: str
    home_score: int
    away_score: int
    half_time_home: int | None
    half_time_away: int | None
    home_stats: CsvTeamStats
    away_stats: CsvTeamStats
    closing: ClosingOdds | None = None

    @property
    def label(self) -> str:
        return f"{self.home_name} — {self.away_name}"

    @property
    def row_key(self) -> str:
        """Identité de la ligne : résultat, puis noms normalisés.

        Le résultat seul ne suffit pas : deux rencontres distinctes peuvent se
        terminer sur le même score le même jour (16 cas mesurés sur les 500
        lignes de la saison). Les noms départagent donc la **ligne** ; la
        décision de rattachement, elle, reste fondée sur le résultat, les noms
        ne servant qu'à confirmer le sens domicile/extérieur.
        """
        mi_temps = (
            f"{self.half_time_home}-{self.half_time_away}"
            if self.half_time_home is not None and self.half_time_away is not None
            else "?"
        )
        return (
            f"{self.division}|{self.played_on.isoformat()}|"
            f"{self.home_score}-{self.away_score}|{mi_temps}|"
            f"{normalize_name(self.home_name)}|{normalize_name(self.away_name)}"
        )


def _price(value: Any) -> float | None:
    """Cote décimale valide : strictement supérieure à 1, jamais inventée."""
    prix = parse_float(value)
    if prix is None or prix <= 1.0 or prix > 1000.0:
        return None
    return prix


def _closing_odds(row: dict[str, str]) -> ClosingOdds | None:
    """Cotes de clôture moyennes ; `None` si le 1X2 n'est pas complet."""
    domicile = _price(row.get("AvgCH"))
    nul = _price(row.get("AvgCD"))
    exterieur = _price(row.get("AvgCA"))
    if domicile is None or nul is None or exterieur is None:
        return None
    return ClosingOdds(
        home=domicile,
        draw=nul,
        away=exterieur,
        over_2_5=_price(row.get("AvgC>2.5")),
        under_2_5=_price(row.get("AvgC<2.5")),
    )


def _team_stats(
    row: dict[str, str],
    *,
    is_home: bool,
    goals_for: int,
    goals_against: int,
) -> CsvTeamStats:
    prefixe = "H" if is_home else "A"
    xg = row.get(f"{prefixe}xG")
    return CsvTeamStats(
        is_home=is_home,
        goals_for=goals_for,
        goals_against=goals_against,
        shots=parse_int(row.get(f"{prefixe}S")),
        shots_on_target=parse_int(row.get(f"{prefixe}ST")),
        corners=parse_int(row.get(f"{prefixe}C")),
        yellow_cards=parse_int(row.get(f"{prefixe}Y")),
        red_cards=parse_int(row.get(f"{prefixe}R")),
        expected_goals=parse_float(xg),
        fouls=parse_int(row.get(f"{prefixe}F")),
    )


def map_row(row: dict[str, str], *, division: str) -> CsvRow | None:
    """Transforme une ligne jouée en rencontre ; `None` si la rencontre n'a pas eu lieu."""
    jour = parse_date(row.get("Date"))
    if jour is None:
        return None
    buts_domicile = parse_int(row.get("FTHG"))
    buts_exterieur = parse_int(row.get("FTAG"))
    if buts_domicile is None or buts_exterieur is None:
        return None
    return CsvRow(
        division=(row.get("Div") or division).upper(),
        played_on=jour,
        kickoff=row.get("Time") or None,
        home_name=(row.get("HomeTeam") or "").strip(),
        away_name=(row.get("AwayTeam") or "").strip(),
        home_score=buts_domicile,
        away_score=buts_exterieur,
        half_time_home=parse_int(row.get("HTHG")),
        half_time_away=parse_int(row.get("HTAG")),
        home_stats=_team_stats(
            row,
            is_home=True,
            goals_for=buts_domicile,
            goals_against=buts_exterieur,
        ),
        away_stats=_team_stats(
            row,
            is_home=False,
            goals_for=buts_exterieur,
            goals_against=buts_domicile,
        ),
        closing=_closing_odds(row),
    )


def parse_rows(text: str, *, division: str) -> list[CsvRow]:
    """Lit le fichier complet et ne garde que les rencontres jouées."""
    lignes = read_dicts(text)
    resultats: list[CsvRow] = []
    for ligne in lignes:
        entree = map_row(ligne, division=division)
        if entree is not None:
            resultats.append(entree)
    if not lignes:
        raise ProviderPayloadError("Le fichier CSV ne contient aucune rencontre.")
    return resultats


def discover_divisions() -> list[dict[str, str | None]]:
    """Catalogue statique des divisions connues (le fournisseur n'a pas d'API)."""
    return [
        {
            "external_id": code,
            "name": fiche["name"],
            "country": fiche["country"],
        }
        for code, fiche in sorted(DIVISIONS.items())
    ]


__all__ = [
    "ALLOWED_HOSTS",
    "BASE_URL",
    "DIVISIONS",
    "ClosingOdds",
    "CsvRow",
    "CsvTeamStats",
    "build_url",
    "discover_divisions",
    "division_label",
    "map_row",
    "parse_rows",
    "season_code",
]
