"""Mapping pur des charges BigBallsData vers les objets normalisés."""

from datetime import UTC, datetime
from typing import Any

from app.connectors.base import NormalizedMatch, NormalizedTeam, NormalizedTeamStats
from app.connectors.matching import normalize_name

STATUS_MAP = {
    "scheduled": "programme",
    "live": "en_cours",
    "in_progress": "en_cours",
    "finished": "termine",
    "postponed": "reporte",
    "cancelled": "annule",
    "suspended": "en_cours",
}


def parse_datetime(value: Any) -> datetime:
    """Analyse une date ISO 8601 et la normalise en UTC."""
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        raise ValueError("Date absente")
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def map_status(raw: Any) -> str:
    """Traduit le statut fournisseur ; inconnu devient `programme`."""
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
    short = raw.get("short_name")
    return NormalizedTeam(
        external_id=str(external_id),
        name=str(name),
        short_name=str(short) if short else None,
    )


def _score(raw: Any) -> tuple[int | None, int | None]:
    if not isinstance(raw, dict):
        return None, None
    home = raw.get("home")
    away = raw.get("away")
    return (
        int(home) if isinstance(home, (int, float)) else None,
        int(away) if isinstance(away, (int, float)) else None,
    )


def map_match(
    raw: dict[str, Any], *, competition_external_id: str, season_label: str
) -> NormalizedMatch:
    """Transforme une rencontre BigBallsData en rencontre normalisée."""
    home = _team(raw.get("home"))
    away = _team(raw.get("away"))
    home_score, away_score = _score(raw.get("score"))
    venue = raw.get("venue")
    raw_status = raw.get("status")
    return NormalizedMatch(
        external_id=str(raw["id"]),
        competition_external_id=competition_external_id,
        season_label=season_label,
        kickoff_at=parse_datetime(raw.get("kickoff_utc")),
        status=map_status(raw_status),
        home=home,
        away=away,
        home_score=home_score,
        away_score=away_score,
        venue=str(venue) if venue else None,
        raw_status=str(raw_status) if raw_status else None,
    )


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def _float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def map_statistics(
    data: dict[str, Any], *, match_external_id: str, home_id: str, away_id: str
) -> list[NormalizedTeamStats]:
    """Transforme les deux lignes de statistiques d'une rencontre terminée."""
    lines: list[NormalizedTeamStats] = []
    for side, is_home, expected_id in (
        ("home", True, home_id),
        ("away", False, away_id),
    ):
        raw = data.get(side)
        if not isinstance(raw, dict):
            continue
        team_id = str(raw.get("team_id") or expected_id)
        extra = {}
        for key in ("pass_percentage", "accurate_passes", "total_passes", "goalkeeper_saves"):
            if raw.get(key) is not None:
                extra[key] = raw[key]
        lines.append(
            NormalizedTeamStats(
                match_external_id=match_external_id,
                team_external_id=team_id,
                is_home=is_home,
                shots=_int(raw.get("total_shots")),
                shots_on_target=_int(raw.get("shots_on_target")),
                possession=_float(raw.get("ball_possession")),
                corners=_int(raw.get("corner_kicks")),
                yellow_cards=_int(raw.get("yellow_cards")),
                red_cards=_int(raw.get("red_cards")),
                expected_goals=_float(raw.get("expected_goals")),
                extra=extra or None,
            )
        )
    return lines


def map_league(raw: dict[str, Any]) -> dict[str, str | None]:
    """Réduit une compétition à ses champs utiles."""
    return {
        "external_id": str(raw.get("id") or ""),
        "name": str(raw.get("name") or ""),
        "country": str(raw["country"]) if raw.get("country") else None,
        "search_key": normalize_name(str(raw.get("name") or "")),
    }
