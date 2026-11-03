"""Configuration centralisée de l'API.

Toutes les valeurs proviennent du fichier `.env` situé à la racine du projet.
Aucun secret ne doit être écrit en dur dans le code.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/app/core/config.py -> racine du projet
PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Paramètres de l'application, lus depuis l'environnement."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "ODDS ANALYST"
    app_version: str = "0.1.0"
    app_env: str = "development"
    app_debug: bool = True
    app_timezone: str = "Europe/Paris"

    # Base de données
    database_url: str = (
        "postgresql+psycopg://odds_analyst_app:mot_de_passe@localhost:5432/odds_analyst"
    )

    # Réseau
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    web_url: str = "http://localhost:3100"

    # Sécurité
    secret_key: str = ""
    session_cookie_name: str = "odds_analyst_session"
    csrf_cookie_name: str = "odds_analyst_csrf"
    session_max_age_seconds: int = 86_400
    cookie_secure: bool = False

    # Limitation des tentatives de connexion
    login_max_attempts: int = 5
    login_window_seconds: int = 900

    # Journalisation
    log_level: str = "INFO"
    log_format: str = "json"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Retourne l'instance unique des paramètres (mise en cache)."""
    return Settings()


settings = get_settings()
