"""Mapping pur des charges football-data.org."""

from datetime import UTC, datetime
from typing import Any

from app.connectors.base import NormalizedMatch, NormalizedTeam

STATUS_MAP = {
    "scheduled": "programme",
    "timed": "programme",
    "in_play": "en_cours",
    "paused": "en_cours",
    "finished": "termine",
    "awarded": "termine",
    "postponed": "reporte",
    "cancelled": "annule",
    "suspended": "en_cours",
}


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        raise ValueError("Date absente")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def map_status(raw: Any) -> str:
    if not isinstance(raw, str):
        return "programme"
    return STATUS_MAP.get(raw.strip().lower(), "programme")


def _team(raw: Any) -> NormalizedTeam:
    if not isinstance(raw, dict):
        raise ValueError("Équipe absente")
    external_id = raw.get("id")
    name = raw.get("name")
    if not external_id or not name:
        raise ValueError("Équipe incomplète")
    short = raw.get("shortName") or raw.get("tla")
    return NormalizedTeam(
        external_id=str(external_id),
        name=str(name),
        short_name=str(short) if short else None,
    )


def _score(raw: Any, key: str) -> tuple[int | None, int | None]:
    if not isinstance(raw, dict):
        return None, None
    block = raw.get(key)
    if not isinstance(block, dict):
        return None, None
    home = block.get("home")
    away = block.get("away")
    return (
        int(home) if isinstance(home, (int, float)) else None,
        int(away) if isinstance(away, (int, float)) else None,
    )


def map_match(raw: dict[str, Any]) -> NormalizedMatch:
    """Transforme une rencontre football-data.org en rencontre normalisée."""
    competition = raw.get("competition")
    if not isinstance(competition, dict) or not competition.get("code"):
        raise ValueError("Compétition absente")
    season = raw.get("season")
    season_label = ""
    if isinstance(season, dict) and season.get("startDate"):
        season_label = str(season["startDate"])[:4]
    elif isinstance(season, dict) and season.get("id"):
        season_label = str(season["id"])

    home = _team(raw.get("homeTeam"))
    away = _team(raw.get("awayTeam"))
    full_home, full_away = _score(raw.get("score"), "fullTime")
    half_home, half_away = _score(raw.get("score"), "halfTime")
    raw_status = raw.get("status")
    venue = raw.get("venue")

    return NormalizedMatch(
        external_id=str(raw["id"]),
        competition_external_id=str(competition["code"]),
        season_label=season_label,
        kickoff_at=parse_datetime(raw.get("utcDate")),
        status=map_status(raw_status),
        home=home,
        away=away,
        home_score=full_home,
        away_score=full_away,
        half_time_home_score=half_home,
        half_time_away_score=half_away,
        venue=str(venue) if venue else None,
        raw_status=str(raw_status) if raw_status else None,
    )


def map_competition(raw: dict[str, Any]) -> dict[str, str | None]:
    return {
        "external_id": str(raw.get("code") or ""),
        "name": str(raw.get("name") or ""),
        "country": None,
    }
