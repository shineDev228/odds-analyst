"""Importateur The Odds API : conversion des cotes normalisées en plan."""

from typing import Any

from app.connectors.base import NormalizedEventOdds


def odds_entry(event: NormalizedEventOdds, match_id: str) -> dict[str, Any]:
    return {
        "match_id": match_id,
        "event_id": event.event_id,
        "bookmaker": event.bookmaker,
        "captured_at": event.captured_at.isoformat(),
        "ignored": event.ignored,
        "markets": [
            {
                "template_code": market.template_code,
                "line": market.line,
                "outcomes": market.outcomes,
            }
            for market in event.markets
        ],
    }
