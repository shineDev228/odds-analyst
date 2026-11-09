"""Schémas du générateur de combinaisons."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

ALLOWED_MARKETS = ("1X2", "DOUBLE_CHANCE", "PLUS_MOINS")
ALLOWED_MARKET_SET = set(ALLOWED_MARKETS)


class CombinationRequest(BaseModel):
    """Critères facultatifs ; les valeurs absentes viennent des préférences."""

    nombre_selections: int | None = Field(default=None, ge=2, le=15)
    cote_min: float | None = Field(default=None, gt=1.0, le=10_000.0)
    cote_max: float | None = Field(default=None, gt=1.0, le=10_000.0)
    marches_autorises: list[str] | None = Field(default=None, max_length=3)
    limite: int = Field(default=10, ge=1, le=50)

    @field_validator("marches_autorises")
    @classmethod
    def _known_markets(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("Sélectionnez au moins un marché.")
        unknown = sorted(set(value) - ALLOWED_MARKET_SET)
        if unknown:
            raise ValueError(f"Marché inconnu : {', '.join(unknown)}.")
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def _range(self) -> "CombinationRequest":
        if (
            self.cote_min is not None
            and self.cote_max is not None
            and self.cote_max <= self.cote_min
        ):
            raise ValueError("La cote maximale doit être supérieure à la cote minimale.")
        return self


class CombinationSelectionRead(BaseModel):
    """Sélection d'une rencontre dans une combinaison."""

    match_id: UUID
    market_id: UUID
    selection_id: UUID
    match_label: str
    competition_name: str
    kickoff_at: datetime
    market_name: str
    selection_label: str
    decimal_odds: float = Field(gt=1.0)
    probability: float = Field(ge=0.0, le=1.0)
    low: float = Field(ge=0.0, le=1.0)
    high: float = Field(ge=0.0, le=1.0)


class CombinationRead(BaseModel):
    """Combinaison générée."""

    selections: list[CombinationSelectionRead]
    total_odds: float = Field(gt=1.0)
    probability: float = Field(ge=0.0, le=1.0)
    low: float = Field(ge=0.0, le=1.0)
    high: float = Field(ge=0.0, le=1.0)
    expected_value: float


class CombinationParameters(BaseModel):
    """Paramètres réellement appliqués."""

    nombre_selections: int
    cote_min: float
    cote_max: float
    marches_autorises: list[str]
    limite: int


class CombinationResponse(BaseModel):
    """Réponse du générateur."""

    combinaisons: list[CombinationRead]
    parametres: CombinationParameters
    matchs_examines: int = Field(ge=0)
    matchs_disponibles: int = Field(ge=0)
    matchs_ignores: int = Field(ge=0)
    selections_disponibles: int = Field(ge=0)
    recherche_tronquee: bool
    message: str
    avertissement: str
