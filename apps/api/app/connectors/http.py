"""Client HTTP partagé des connecteurs : délais, réessais, rédaction.

Aucun module de ce fichier ne journalise d'en-tête d'authentification ni d'URL
complète. Les tests injectent un transport `httpx.MockTransport`.
"""

import logging
import re
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.connectors.base import (
    ConnectorError,
    ProviderAuthError,
    ProviderPayloadError,
    ProviderRateLimitError,
)

logger = logging.getLogger("odds_analyst.connectors")

REDACTED = "***"

_SECRET_PATTERN = re.compile(
    r"(apiKey|api_key|x-api-key|X-Auth-Token|token|key)=([^&\s\"']+)",
    re.IGNORECASE,
)


def redact(value: str) -> str:
    """Masque toute valeur ressemblant à une clé dans un texte de journal."""
    return _SECRET_PATTERN.sub(lambda m: f"{m.group(1)}={REDACTED}", value)


def host_only(url: str) -> str:
    """Réduit une URL à son hôte, sans chemin ni paramètres."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


class HttpClient:
    """Petit client JSON avec réessais bornés et espacement minimal."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        max_retries: int = 2,
        min_interval: float = 0.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._min_interval = min_interval
        self._sleep = sleep
        self._last_call: float | None = None
        self._client = httpx.Client(
            timeout=timeout, transport=transport, follow_redirects=True
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _throttle(self) -> None:
        if self._min_interval <= 0 or self._last_call is None:
            return
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            self._sleep(self._min_interval - elapsed)

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        provider: str = "connector",
    ) -> tuple[Any, httpx.Headers]:
        """Exécute un GET et renvoie la charge JSON et les en-têtes de réponse."""
        response = self._get(url, params=params, headers=headers, provider=provider)
        try:
            return response.json(), response.headers
        except ValueError as exc:
            raise ProviderPayloadError(
                "La réponse du fournisseur est illisible."
            ) from exc

    def get_bytes(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        provider: str = "connector",
    ) -> tuple[bytes, httpx.Headers]:
        """Exécute un GET et renvoie le corps brut et les en-têtes de réponse."""
        response = self._get(url, params=params, headers=headers, provider=provider)
        return response.content, response.headers

    def _get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        provider: str = "connector",
    ) -> httpx.Response:
        """Exécute un GET avec réessais bornés et erreurs traduites."""
        attempt = 0
        while True:
            self._throttle()
            try:
                response = self._client.get(url, params=params, headers=headers)
                self._last_call = time.monotonic()
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    logger.warning("%s: erreur réseau (%s)", provider, type(exc).__name__)
                    raise ConnectorError(
                        "Le fournisseur est injoignable. Réessayez plus tard."
                    ) from exc
                self._sleep(0.5 if attempt == 0 else 1.5)
                attempt += 1
                continue

            if response.status_code == 429:
                raise ProviderRateLimitError(
                    "Le quota du fournisseur est épuisé. Réessayez après réinitialisation."
                )
            if response.status_code in {401, 403}:
                raise ProviderAuthError(
                    "La clé du fournisseur est absente ou refusée. "
                    "Vérifiez le fichier .env puis redémarrez l'API."
                )
            if response.status_code >= 500 and attempt < self._max_retries:
                self._sleep(0.5 if attempt == 0 else 1.5)
                attempt += 1
                continue
            if response.status_code >= 400:
                logger.warning(
                    "%s: réponse %s sur %s", provider, response.status_code, host_only(url)
                )
                raise ConnectorError(
                    f"Le fournisseur a refusé la requête ({response.status_code})."
                )
            return response
