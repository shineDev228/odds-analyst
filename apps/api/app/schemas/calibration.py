"""Schémas du rétro-test de calibration."""

from datetime import datetime

from pydantic import BaseModel, Field


class CalibrationBinRead(BaseModel):
    """Tranche de probabilité et fréquence observée."""

    low: float = Field(ge=0.0, le=1.0)
    high: float = Field(ge=0.0, le=1.0)
    count: int = Field(ge=0)
    mean_predicted: float = Field(ge=0.0, le=1.0)
    observed: float = Field(ge=0.0, le=1.0)
    wilson_low: float = Field(ge=0.0, le=1.0)
    wilson_high: float = Field(ge=0.0, le=1.0)


class CalibrationRead(BaseModel):
    """Synthèse de calibration et tableau de fiabilité."""

    model_version: str
    generated_at: datetime
    limit: int
    matches_evaluated: int = Field(ge=0)
    matches_excluded: int = Field(ge=0)
    period_start: datetime | None
    period_end: datetime | None
    home_wins: int = Field(ge=0)
    draws: int = Field(ge=0)
    away_wins: int = Field(ge=0)
    brier: float | None
    log_loss: float | None
    accuracy: float | None
    baseline_brier: float | None
    baseline_log_loss: float | None
    brier_skill: float | None
    ece: float | None
    mean_xg_coverage: float | None
    bins: list[CalibrationBinRead]
    message: str
    avertissement: str
