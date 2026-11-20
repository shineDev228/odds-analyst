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
        self,
        *,
        league: str,
        season: str,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "sport": "football",
            "league": league,
            "season": season,
            "limit": limit,
            "offset": offset,
        }
        if status:
            params["status"] = status
        data = self._get("/v1/matches", params)
        return [item for item in data if isinstance(item, dict)]

    def get_statistics(self, match_id: str) -> dict[str, Any]:
        data = self._get(f"/v1/matches/{match_id}/statistics")
        return data if isinstance(data, dict) else {}

    def list_teams(self, *, league: str) -> list[dict[str, Any]]:
        data = self._get("/v1/teams", {"sport": "football", "league": league})
        return [item for item in data if isinstance(item, dict)]

    def get_standings(self, *, league: str, season: str) -> list[dict[str, Any]]:
        """Renvoie les lignes de classement de la première compétition servie."""
        data = self._get("/v1/standings", {"league": league, "season": season})
        standings = data.get("standings") if isinstance(data, dict) else None
        if not isinstance(standings, list) or not standings:
            return []
        first = standings[0]
        rows = first.get("rows") if isinstance(first, dict) else None
        return [row for row in rows or [] if isinstance(row, dict)]

    def get_team_elo(self, team_id: str) -> dict[str, Any]:
        """Force Elo du jour ; le fournisseur la recalcule par lots."""
        data = self._get(f"/v1/teams/{team_id}/elo")
        return data if isinstance(data, dict) else {}

    def get_team_stats(self, team_id: str) -> dict[str, Any]:
        """Cumul de tous les matchs conservés par le fournisseur."""
        data = self._get(f"/v1/teams/{team_id}/stats", {"sport": "football"})
        return data if isinstance(data, dict) else {}

    def get_team_season(self, team_id: str) -> dict[str, Any]:
        """Splits de la saison en cours et dix derniers matchs."""
        data = self._get(f"/v1/teams/{team_id}/season", {"sport": "football"})
        return data if isinstance(data, dict) else {}

    def list_games(self, *, league: str, day: str) -> list[dict[str, Any]]:
        """Rencontres d'une compétition et d'une date UTC, cotes agrégées incluses."""
        data = self._get(
            "/v1/games",
            {"sport": "football", "league": league, "date": day},
        )
        games = data.get("games") if isinstance(data, dict) else None
        return [game for game in games or [] if isinstance(game, dict)]

    def get_usage(self) -> dict[str, Any]:
        """Quota réel annoncé par le fournisseur, pour recaler le compteur local."""
        data = self._get("/v1/usage")
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
