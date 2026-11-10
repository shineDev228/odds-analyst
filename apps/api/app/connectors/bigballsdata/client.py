"""Client BigBallsData : compétitions, rencontres et statistiques."""

from typing import Any

from app.connectors.base import ProviderPayloadError, QuotaInfo
from app.connectors.http import HttpClient


class BigBallsDataClient:
    """Accès en lecture seule à l'API BigBallsData."""

    provider = "bigballsdata"

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
        return {"x-api-key": self._api_key, "accept": "application/json"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        payload, headers = self._http.get_json(
            f"{self._base_url}{path}",
            params=params,
            headers=self._headers(),
            provider=self.provider,
        )
        if not isinstance(payload, dict) or "data" not in payload:
            raise ProviderPayloadError("Réponse BigBallsData incomplète.")
        self.last_quota = QuotaInfo(
            used=0,
            remaining=_header_int(headers, "x-ratelimit-remaining"),
            limit=None,
        )
        return payload["data"]

    def list_leagues(self) -> list[dict[str, Any]]:
        data = self._get("/v1/leagues", {"sport": "football"})
        return [item for item in data if isinstance(item, dict)]

    def list_matches(
        self, *, league: str, season: str, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        data = self._get(
            "/v1/matches",
            {
                "sport": "football",
                "league": league,
                "season": season,
                "limit": limit,
                "offset": offset,
            },
        )
        return [item for item in data if isinstance(item, dict)]

    def get_statistics(self, match_id: str) -> dict[str, Any]:
        data = self._get(f"/v1/matches/{match_id}/statistics")
        return data if isinstance(data, dict) else {}


def _header_int(headers: Any, name: str) -> int | None:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


__all__ = ["BigBallsDataClient"]
