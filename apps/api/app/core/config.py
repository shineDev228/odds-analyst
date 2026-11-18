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
    app_version: str = "1.1.0"
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
    # Expiration d'inactivité : une session sans requête est fermée.
    session_idle_seconds: int = 43_200
    # Fréquence minimale d'écriture de `last_seen_at`.
    session_touch_seconds: int = 60
    cookie_secure: bool = False
    # HSTS n'a de sens qu'en HTTPS ; il suit donc `cookie_secure`.
    hsts_max_age_seconds: int = 63_072_000

    # Limitation des tentatives de connexion
    login_max_attempts: int = 5
    login_window_seconds: int = 900

    # Journalisation
    log_level: str = "INFO"
    log_format: str = "json"

    # Sources de données — les clés vivent uniquement dans `.env`.
    bigballsdata_key: str = ""
    bigballsdata_base_url: str = "https://api.bigballsdata.com"
    # Saison demandée au fournisseur : « 2026 » désigne 2026-2027.
    bigballsdata_season: str = "2026"
    the_odds_api_key: str = ""
    the_odds_api_base_url: str = "https://api.the-odds-api.com/v4"
    football_data_key: str = ""
    football_data_base_url: str = "https://api.football-data.org/v4"
    # Fichiers CSV publics : aucune clé, aucun quota.
    football_data_uk_base_url: str = "https://football-data.co.uk"
    # Dossier des fichiers CSV conservés ; vide = `data/local/csv`.
    csv_storage_dir: str = ""

    # Mise à jour automatique au démarrage de l'API (phase 15, étape 6).
    # Une seule passe de faits et de CSV, jamais les cotes 1xBet.
    auto_sync_enabled: bool = True
    auto_sync_interval_hours: float = 24
    auto_sync_check_minutes: int = 60
    auto_sync_startup_delay_seconds: int = 30
    auto_sync_stats_limit: int = 20

    # Budgets locaux (réserves déjà déduites).
    # BigBallsData autorise 2 000 requêtes par jour ; le plafond local garde
    # 10 % de marge pour les reprises et les erreurs.
    bigballsdata_daily_budget: int = 1800
    the_odds_api_monthly_budget: int = 400
    football_data_minute_budget: int = 8

    # Réseau des connecteurs.
    connector_timeout_seconds: float = 15.0
    connector_max_retries: int = 2
    connector_preview_ttl_seconds: int = 7200
    connector_max_extended_events: int = 20
    connector_max_stats_batch: int = 10

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Retourne l'instance unique des paramètres (mise en cache)."""
    return Settings()


settings = get_settings()
