"""Routes de synchronisation : faits BigBallsData, cotes The Odds API, CSV."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.core import deps
from app.core.config import settings
from app.schemas.sync import (
    CsvDownloadRead,
    CsvOverviewRead,
    CsvReportRead,
    CsvRequest,
    OddsOverviewRead,
    OddsPreviewRead,
    OddsReportRead,
    OddsRequest,
    SyncOverviewRead,
    SyncReportRead,
    SyncRequest,
    SyncRunRead,
)
from app.services import csv_sync, odds_sync
from app.services import synchronization as service

router = APIRouter(
    prefix="/sync",
    tags=["Synchronisation"],
    dependencies=[Depends(deps.get_auth_context), Depends(deps.verify_csrf)],
)


@router.get("/overview", response_model=SyncOverviewRead)
def overview(db: deps.DbSession) -> SyncOverviewRead:
    """État des sept compétitions, quota local et derniers journaux."""
    return SyncOverviewRead.model_validate(service.overview(db))


@router.get("/runs", response_model=list[SyncRunRead])
def list_runs(
    db: deps.DbSession,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[SyncRunRead]:
    return [SyncRunRead.model_validate(run) for run in service.recent_runs(db, limit)]


@router.post("/run", response_model=SyncReportRead)
def run(payload: SyncRequest, db: deps.DbSession) -> SyncReportRead:
    """Importe les compétitions demandées, sans jamais dépasser le budget local."""
    report = service.run_sync(
        db,
        leagues=payload.leagues or None,
        include_stats=payload.include_stats,
        include_standings=payload.include_standings,
        stats_limit=payload.stats_limit,
    )
    db.commit()
    return SyncReportRead.model_validate(report.as_dict())


@router.get("/odds/overview", response_model=OddsOverviewRead)
def odds_overview(db: deps.DbSession) -> OddsOverviewRead:
    """Quota mensuel, coûts, couverture et dernier journal des cotes."""
    return OddsOverviewRead.model_validate(odds_sync.overview(db))


@router.post("/odds/preview", response_model=OddsPreviewRead)
def odds_preview(
    db: deps.DbSession,
    payload: Annotated[OddsRequest | None, Body()] = None,
) -> OddsPreviewRead:
    """Appariement à blanc : aucun crédit consommé, aucune écriture."""
    if not settings.the_odds_api_key:
        raise HTTPException(
            status_code=503,
            detail="Clé The Odds API absente : renseignez THE_ODDS_API_KEY puis redémarrez l'API.",
        )
    request = payload or OddsRequest()
    report = odds_sync.preview(
        db,
        leagues=request.leagues or None,
        include_extended=request.include_extended,
        extended_limit=request.extended_limit,
    )
    return OddsPreviewRead.model_validate(report.as_dict())


@router.post("/odds/run", response_model=OddsReportRead)
def odds_run(
    db: deps.DbSession,
    payload: Annotated[OddsRequest | None, Body()] = None,
) -> OddsReportRead:
    """Importe les cotes 1xBet des rencontres à venir, dans le budget local."""
    if not settings.the_odds_api_key:
        raise HTTPException(
            status_code=503,
            detail="Clé The Odds API absente : renseignez THE_ODDS_API_KEY puis redémarrez l'API.",
        )
    request = payload or OddsRequest()
    report = odds_sync.run(
        db,
        leagues=request.leagues or None,
        include_extended=request.include_extended,
        extended_limit=request.extended_limit,
    )
    db.commit()
    return OddsReportRead.model_validate(report.as_dict())


@router.get("/csv/overview", response_model=CsvOverviewRead)
def csv_overview(db: deps.DbSession) -> CsvOverviewRead:
    """Fichiers conservés, couverture du xG et lignes en attente de décision."""
    return CsvOverviewRead.model_validate(csv_sync.overview(db))


@router.post("/csv/download", response_model=CsvDownloadRead)
def csv_download(
    db: deps.DbSession,
    payload: Annotated[CsvRequest | None, Body()] = None,
) -> CsvDownloadRead:
    """Télécharge les fichiers publics et les conserve, sans écrire en base."""
    request = payload or CsvRequest()
    report = csv_sync.download(db, leagues=request.leagues or None)
    db.commit()
    return CsvDownloadRead.model_validate(report.as_dict())


@router.post("/csv/run", response_model=CsvReportRead)
def csv_run(
    db: deps.DbSession,
    payload: Annotated[CsvRequest | None, Body()] = None,
) -> CsvReportRead:
    """Écrit le xG et les cotes de clôture des rencontres terminées."""
    request = payload or CsvRequest()
    report = csv_sync.run(
        db,
        leagues=request.leagues or None,
        refresh=request.refresh,
    )
    db.commit()
    return CsvReportRead.model_validate(report.as_dict())
