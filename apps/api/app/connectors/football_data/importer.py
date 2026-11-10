"""Importateur football-data.org : transformation en plan d'écriture."""

from typing import Any

from app.connectors.base import NormalizedMatch


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
