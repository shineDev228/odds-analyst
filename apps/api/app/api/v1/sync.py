"""Routes de synchronisation : une seule source de faits, BigBallsData."""

from fastapi import APIRouter, Depends, Query

from app.core import deps
from app.schemas.sync import (
    SyncOverviewRead,
    SyncReportRead,
    SyncRequest,
    SyncRunRead,
)
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
