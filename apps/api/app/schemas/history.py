"""Schémas de l'historique des combinaisons et de la performance."""

from datetime import datetime
from uuid import UUID

from engine.settlement import CombinationStatus, LegStatus
from pydantic import BaseModel, Field, model_validator

from app.schemas.combination import CombinationParameters


class SavedSelectionInput(BaseModel):
    """Référence d'une sélection à enregistrer, avec la cote affichée."""

    match_id: UUID
    selection_id: UUID
    decimal_odds: float = Field(gt=1.0)


class CombinationSaveRequest(BaseModel):
    """Combinaison générée que l'utilisateur souhaite conserver."""

    selections: list[SavedSelectionInput] = Field(min_length=2, max_length=15)
    parametres: CombinationParameters
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _coherence(self) -> "CombinationSaveRequest":
        if len(self.selections) != self.parametres.nombre_selections:
            raise ValueError(
                "Le nombre de sélections ne correspond pas aux paramètres enregistrés."
            )
        match_ids = [item.match_id for item in self.selections]
        if len(set(match_ids)) != len(match_ids):
            raise ValueError("Une seule sélection par rencontre est autorisée.")
        return self


class SavedLegRead(BaseModel):
    """Jambe enregistrée, avec son règlement actuel."""

    id: UUID
    position: int
    match_id: UUID | None
    market_id: UUID | None
    selection_id: UUID | None
    match_label: str
    competition_name: str
    kickoff_at: datetime
    market_name: str
    market_family: str
    market_period: str
    selection_code: str
    selection_label: str
    line: float | None
    decimal_odds: float
    probability: float
    low: float
    high: float
    status: LegStatus
    status_label: str
    reason: str
    home_score: int | None
    away_score: int | None


class SavedCombinationRead(BaseModel):
    """Combinaison enregistrée et son règlement dérivé."""

    id: UUID
    created_at: datetime
    nombre_selections: int
    cote_min: float
    cote_max: float
    marches_autorises: list[str]
    total_odds: float
    probability: float
    low: float
    high: float
    expected_value: float
    note: str | None
    status: CombinationStatus
    status_label: str
    effective_odds: float
    payout_units: float | None
    net_units: float | None
    selections: list[SavedLegRead]


class PerformanceSummaryRead(BaseModel):
    """Synthèse en unités de mise, sans montant en argent."""

    total: int
    en_attente: int
    gagnees: int
    perdues: int
    remboursees: int
    indisponibles: int
    reglees: int
    taux_reussite: float | None
    cote_moyenne: float | None
    unites_engagees: float
    unites_retournees: float
    resultat_net: float
    roi: float | None
    avertissement: str
