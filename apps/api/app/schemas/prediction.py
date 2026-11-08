"""Schémas de la prédiction statistique.

Toute probabilité est accompagnée d'une fourchette basse/haute : aucune sortie
ne doit être présentée comme certaine.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PredictionSelection(BaseModel):
    """Probabilité estimée d'une sélection et sa fourchette à 80 %."""

    code: str
    label: str
    probability: float = Field(ge=0.0, le=1.0)
    low: float = Field(ge=0.0, le=1.0)
    high: float = Field(ge=0.0, le=1.0)


class PredictionTotal(BaseModel):
    """Marché plus / moins pour une ligne de buts."""

    line: float
    over: PredictionSelection
    under: PredictionSelection


class PredictionScoreline(BaseModel):
    """Score exact estimé."""

    label: str
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    probability: float = Field(ge=0.0, le=1.0)


class PredictionQuality(BaseModel):
    """Qualité de l'échantillon utilisé par le modèle."""

    level: str
    label: str
    matches_home: int = Field(ge=0)
    matches_away: int = Field(ge=0)
    effective_home: float = Field(ge=0.0)
    effective_away: float = Field(ge=0.0)
    warnings: list[str]


class PredictionRead(BaseModel):
    """Analyse statistique complète d'une rencontre."""

    match_id: UUID
    model_version: str
    computed_at: datetime
    expected_goals_home: float = Field(gt=0.0)
    expected_goals_away: float = Field(gt=0.0)
    expected_goals_total: float = Field(gt=0.0)
    quality: PredictionQuality
    resultat: list[PredictionSelection]
    double_chance: list[PredictionSelection]
    totaux: list[PredictionTotal]
    btts: list[PredictionSelection]
    scores_exacts: list[PredictionScoreline]
    config: dict[str, float | int | str]
    avertissement: str
