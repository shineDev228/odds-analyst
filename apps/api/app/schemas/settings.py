"""Schémas des paramètres applicatifs."""

from pydantic import BaseModel, Field, model_validator


class PreferencesRead(BaseModel):
    cote_min: float = Field(default=50.0, ge=1.0, le=10_000.0)
    cote_max: float = Field(default=100.0, ge=1.0, le=10_000.0)
    nb_selections_defaut: int = Field(default=8, ge=2, le=15)
    marches_autorises: list[str] = Field(
        default_factory=lambda: ["1X2", "DOUBLE_CHANCE", "PLUS_MOINS", "BTTS"]
    )
    demi_vie_jours: int = Field(default=240, ge=30, le=730)
    nb_matchs_historique: int = Field(default=38, ge=5, le=100)

    @model_validator(mode="after")
    def _check_range(self) -> "PreferencesRead":
        if self.cote_max <= self.cote_min:
            raise ValueError("La cote maximale doit être supérieure à la cote minimale.")
        return self


class PreferencesUpdate(PreferencesRead):
    pass
