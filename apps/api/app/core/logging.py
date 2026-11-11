"""Journalisation structurée de l'API.

Aucune donnée sensible n'est journalisée : ni corps de requête, ni en-tête
d'authentification, ni clé de fournisseur. Chaque ligne peut porter un
identifiant de requête pour relier les événements entre eux.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings

# Identifiant de la requête en cours, partagé par les middlewares.
request_id_context: ContextVar[str] = ContextVar("request_id", default="-")

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Une ligne JSON par événement, lisible par un script."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_context.get()
        if request_id and request_id != "-":
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Configure la racine des journaux une seule fois par processus."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _CONFIGURED = True
