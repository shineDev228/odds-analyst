"""Lecture des préférences applicatives, avec valeurs par défaut."""

from sqlalchemy.orm import Session

from app.db.seed import DEFAULT_SETTINGS
from app.models.settings import AppSetting
from app.schemas.settings import PreferencesRead

PREFERENCES_KEY = "preferences"


def get_preferences(db: Session) -> PreferencesRead:
    """Retourne les préférences enregistrées, complétées par les défauts."""
    row = db.get(AppSetting, PREFERENCES_KEY)
    data = (
        row.value
        if row is not None and isinstance(row.value, dict)
        else DEFAULT_SETTINGS[PREFERENCES_KEY]
    )
    return PreferencesRead.model_validate({**DEFAULT_SETTINGS[PREFERENCES_KEY], **data})
