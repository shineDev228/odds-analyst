"""Client football-data.co.uk : téléchargement d'un fichier CSV public."""

from app.connectors.base import QuotaInfo
from app.connectors.football_data_uk.csvar import decode_bytes
from app.connectors.football_data_uk.mapping import CsvRow, build_url, parse_rows
from app.connectors.http import HttpClient


class FootballDataUkClient:
    """Accès en lecture seule à un fichier de résultats et statistiques."""

    provider = "football_data_uk"

    def __init__(self, *, base_url: str, http: HttpClient) -> None:
        self._base_url = base_url
        self._http = http
        self.last_quota: QuotaInfo | None = QuotaInfo(
            used=0, remaining=None, limit=None, reset_at=None
        )

    @property
    def configured(self) -> bool:
        """Aucune clé n'est nécessaire : le fournisseur est toujours prêt."""
        return True

    def close(self) -> None:
        self._http.close()

    def fetch_rows(self, *, division: str, season: str) -> list[CsvRow]:
        """Télécharge le fichier de la division et renvoie les rencontres jouées."""
        url = build_url(self._base_url, division, season)
        contenu, _ = self._http.get_bytes(
            url,
            headers={"accept": "text/csv,*/*"},
            provider=self.provider,
        )
        return parse_rows(decode_bytes(contenu), division=division)


__all__ = ["FootballDataUkClient"]
