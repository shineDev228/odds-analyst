"""Mapping pur des charges BigBallsData vers les objets normalisés.

Aucune valeur n'est inventée : un champ absent reste ``None``. Le xG est
volontairement ignoré — il ne vient pas de BigBallsData mais du CSV, sur la
même ligne que le score.
"""

from datetime import UTC, datetime
from typing import Any

from app.connectors.base import (
    NormalizedMatch,
    NormalizedStanding,
    NormalizedTeam,
    NormalizedTeamStats,
)

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
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def map_status(raw: Any) -> str:
    """Traduit le statut fournisseur ; inconnu devient `programme`."""
    if not isinstance(raw, str):
        return "programme"
    return STATUS_MAP.get(raw.strip().lower(), "programme")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def _float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def map_team(raw: Any) -> NormalizedTeam:
    if not isinstance(raw, dict):
        raise ValueError("Équipe absente")
    external_id = raw.get("id")
    name = raw.get("name")
    if not external_id or not name:
        raise ValueError("Équipe incomplète")
    return NormalizedTeam(
        external_id=str(external_id),
        name=str(name),
        short_name=_text(raw.get("short_name")),
        logo_url=_text(raw.get("logo_url")),
    )


def _score(raw: Any) -> tuple[int | None, int | None]:
    if not isinstance(raw, dict):
        return None, None
    return _int(raw.get("home")), _int(raw.get("away"))


def _half_time(raw: Any) -> tuple[int | None, int | None]:
    """BigBallsData donne les buts par mi-temps ; l'index 0 est la mi-temps."""
    if not isinstance(raw, dict):
        return None, None
    home = raw.get("home")
    away = raw.get("away")
    home_first = home[0] if isinstance(home, list) and home else None
    away_first = away[0] if isinstance(away, list) and away else None
    return _int(home_first), _int(away_first)


def map_match(
    raw: dict[str, Any], *, competition_external_id: str, season_label: str
) -> NormalizedMatch:
    """Transforme une rencontre BigBallsData en rencontre normalisée."""
    home = map_team(raw.get("home"))
    away = map_team(raw.get("away"))
    home_score, away_score = _score(raw.get("score"))
    half_home, half_away = _half_time(raw.get("linescore"))
    has_odds = raw.get("has_odds")
    attendance = _int(raw.get("attendance"))
    return NormalizedMatch(
        external_id=str(raw["id"]),
        competition_external_id=competition_external_id,
        season_label=season_label,
        kickoff_at=parse_datetime(raw.get("kickoff_utc")),
        status=map_status(raw.get("status")),
        home=home,
        away=away,
        home_score=home_score,
        away_score=away_score,
        half_time_home_score=half_home,
        half_time_away_score=half_away,
        round_name=_text(raw.get("round")),
        broadcast=_text(raw.get("broadcast")),
        attendance=attendance if attendance is not None and attendance >= 0 else None,
        has_odds=has_odds if isinstance(has_odds, bool) else None,
        raw_status=_text(raw.get("status")),
    )


STATS_FIELDS = (
    "shots_on_target",
    "shots_off_target",
    "blocked_shots",
    "shots_inside_box",
    "shots_outside_box",
    "fouls",
    "corner_kicks",
    "offsides",
    "yellow_cards",
    "red_cards",
    "goalkeeper_saves",
    "total_passes",
    "accurate_passes",
)


def map_statistics(
    data: dict[str, Any], *, match_external_id: str, home_id: str, away_id: str
) -> list[NormalizedTeamStats]:
    """Transforme les deux lignes de statistiques d'une rencontre.

    BigBallsData ne fournit pas de xG : le champ reste vide, jamais nul.
    """
    lines: list[NormalizedTeamStats] = []
    for side, is_home, expected_id in (
        ("home", True, home_id),
        ("away", False, away_id),
    ):
        raw = data.get(side)
        if not isinstance(raw, dict):
            continue
        values = {field: _int(raw.get(field)) for field in STATS_FIELDS}
        lines.append(
            NormalizedTeamStats(
                match_external_id=match_external_id,
                team_external_id=str(raw.get("team_id") or expected_id),
                is_home=is_home,
                shots=_int(raw.get("total_shots")),
                shots_on_target=values["shots_on_target"],
                shots_off_target=values["shots_off_target"],
                blocked_shots=values["blocked_shots"],
                shots_inside_box=values["shots_inside_box"],
                shots_outside_box=values["shots_outside_box"],
                possession=_float(raw.get("ball_possession")),
                corners=values["corner_kicks"],
                fouls=values["fouls"],
                offsides=values["offsides"],
                yellow_cards=values["yellow_cards"],
                red_cards=values["red_cards"],
                goalkeeper_saves=values["goalkeeper_saves"],
                passes=values["total_passes"],
                accurate_passes=values["accurate_passes"],
                pass_percentage=_float(raw.get("pass_percentage")),
            )
        )
    return lines


def map_standing_row(raw: Any) -> NormalizedStanding:
    if not isinstance(raw, dict) or not raw.get("team_id"):
        raise ValueError("Ligne de classement incomplète")
    draws = raw.get("ties")
    return NormalizedStanding(
        team_external_id=str(raw["team_id"]),
        rank=_int(raw.get("rank")),
        played=_int(raw.get("games_played")),
        wins=_int(raw.get("wins")),
        draws=_int(draws),
        losses=_int(raw.get("losses")),
        goals_for=_int(raw.get("points_for")),
        goals_against=_int(raw.get("points_against")),
        form_string=_text(raw.get("streak")),
    )


def map_league(raw: dict[str, Any]) -> dict[str, str | None]:
    """Réduit une compétition BigBallsData à ses champs utiles."""
    code = raw.get("id")
    name = raw.get("name")
    if not code or not name:
        raise ValueError("Compétition incomplète")
    return {
        "code": str(code),
        "name": str(name),
        "country": _text(raw.get("country")),
    }
