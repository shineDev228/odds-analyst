"""Importateur BigBallsData : transformation des objets normalisés en plan."""

from datetime import datetime
from typing import Any

from app.connectors.base import NormalizedMatch, NormalizedTeamStats


def match_entry(match: NormalizedMatch, season_id: str) -> dict[str, Any]:
    return {
        "external_id": match.external_id,
        "season_id": season_id,
        "kickoff_at": match.kickoff_at.isoformat(),
        "status": match.status,
        "home_external_id": match.home.external_id,
        "home_name": match.home.name,
        "home_short_name": match.home.short_name,
        "away_external_id": match.away.external_id,
        "away_name": match.away.name,
        "away_short_name": match.away.short_name,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "half_time_home_score": match.half_time_home_score,
        "half_time_away_score": match.half_time_away_score,
        "venue": match.venue,
        "raw_status": match.raw_status,
    }


def stats_entry(
    match_id: str,
    lines: list[NormalizedTeamStats],
    team_ids: dict[str, str],
    scores: tuple[int | None, int | None] = (None, None),
) -> dict[str, Any]:
    rows = []
    for line in lines:
        rows.append(
            {
                "team_external_id": line.team_external_id,
                "team_id": team_ids.get(line.team_external_id),
                "is_home": line.is_home,
                "goals_for": scores[0] if line.is_home else scores[1],
                "goals_against": scores[1] if line.is_home else scores[0],
                "shots": line.shots,
                "shots_on_target": line.shots_on_target,
                "possession": line.possession,
                "corners": line.corners,
                "yellow_cards": line.yellow_cards,
                "red_cards": line.red_cards,
                "expected_goals": line.expected_goals,
                "extra": line.extra,
            }
        )
    return {"match_id": match_id, "stats": rows}


def iso(value: datetime) -> str:
    return value.isoformat()
