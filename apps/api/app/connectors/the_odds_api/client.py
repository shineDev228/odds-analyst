"""Client The Odds API : sports, événements, cotes et crédits."""

from typing import Any

from app.connectors.base import ProviderPayloadError, QuotaInfo
from app.connectors.http import HttpClient


class TheOddsApiClient:
    """Accès en lecture seule à The Odds API, filtré plus tard sur 1xBet."""

    provider = "the_odds_api"

    def __init__(self, *, api_key: str, base_url: str, http: HttpClient) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._http = http
        self.last_quota: QuotaInfo | None = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = dict(params or {})
        query["apiKey"] = self._api_key
        payload, headers = self._http.get_json(
            f"{self._base_url}{path}",
            params=query,
            provider=self.provider,
        )
        self.last_quota = QuotaInfo(
            used=_header_int(headers, "x-requests-used") or 0,
            remaining=_header_int(headers, "x-requests-remaining"),
            limit=None,
        )
        return payload

    def list_sports(self) -> list[dict[str, Any]]:
        payload = self._get("/sports")
        if not isinstance(payload, list):
            raise ProviderPayloadError("Liste des sports The Odds API illisible.")
        return [item for item in payload if isinstance(item, dict)]

    def list_events(self, sport_key: str) -> list[dict[str, Any]]:
        payload = self._get(f"/sports/{sport_key}/events")
        if not isinstance(payload, list):
            raise ProviderPayloadError("Liste des événements The Odds API illisible.")
        return [item for item in payload if isinstance(item, dict)]

    def competition_odds(self, sport_key: str, markets: str = "h2h,totals") -> list[dict[str, Any]]:
        payload = self._get(
            f"/sports/{sport_key}/odds",
            {
                "regions": "eu",
                "markets": markets,
                "oddsFormat": "decimal",
                "dateFormat": "iso",
            },
        )
        if not isinstance(payload, list):
            raise ProviderPayloadError("Cotes The Odds API illisibles.")
        return [item for item in payload if isinstance(item, dict)]

    def event_odds(
        self, sport_key: str, event_id: str, markets: str = "double_chance,btts"
    ) -> dict[str, Any]:
        payload = self._get(
            f"/sports/{sport_key}/events/{event_id}/odds",
            {
                "regions": "eu",
                "markets": markets,
                "oddsFormat": "decimal",
                "dateFormat": "iso",
            },
        )
        if not isinstance(payload, dict):
            raise ProviderPayloadError("Cotes The Odds API illisibles.")
        return payload


def _header_int(headers: Any, name: str) -> int | None:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None
