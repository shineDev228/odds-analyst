"""Client football-data.org : repli calendrier et résultats.

La limite gratuite est de 10 requêtes par minute ; le client espace les appels
de 7,5 secondes pour rester sous le plafond même en cas d'enchaînement.
"""

from typing import Any

from app.connectors.base import ProviderPayloadError, QuotaInfo
from app.connectors.http import HttpClient

MIN_INTERVAL_SECONDS = 7.5


class FootballDataClient:
    """Accès en lecture seule à football-data.org."""

    provider = "football_data"

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

    def _headers(self) -> dict[str, str]:
        return {"X-Auth-Token": self._api_key, "accept": "application/json"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        payload, headers = self._http.get_json(
            f"{self._base_url}{path}",
            params=params,
            headers=self._headers(),
            provider=self.provider,
        )
        self.last_quota = QuotaInfo(
            used=0,
            remaining=_header_int(headers, "x-requests-available-minute"),
            limit=_header_int(headers, "x-requests-available-minute"),
        )
        return payload

    def list_competitions(self) -> list[dict[str, Any]]:
        payload = self._get("/competitions")
        if not isinstance(payload, dict):
            raise ProviderPayloadError("Liste des compétitions illisible.")
        competitions = payload.get("competitions")
        if not isinstance(competitions, list):
            raise ProviderPayloadError("Liste des compétitions illisible.")
        return [item for item in competitions if isinstance(item, dict)]

    def list_matches(self, code: str, season: str | None = None) -> list[dict[str, Any]]:
        params = {"season": season} if season else None
        payload = self._get(f"/competitions/{code}/matches", params)
        if not isinstance(payload, dict):
            raise ProviderPayloadError("Liste des rencontres illisible.")
        matches = payload.get("matches")
        if not isinstance(matches, list):
            raise ProviderPayloadError("Liste des rencontres illisible.")
        return [item for item in matches if isinstance(item, dict)]


def _header_int(headers: Any, name: str) -> int | None:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


__all__ = ["MIN_INTERVAL_SECONDS", "FootballDataClient"]
