"""Routes des connecteurs de données."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1._helpers import commit_or_conflict, not_found
from app.connectors.base import ConnectorError
from app.core import deps
from app.schemas.connector import (
    ApplyPreviewRead,
    ConnectorLinkCreate,
    ConnectorLinkRead,
    ConnectorLinkUpdate,
    ConnectorOverviewRead,
    DiscoveredCompetitionRead,
    EventLinkRequest,
    ExtendedOddsRequest,
    FixturesPreviewRead,
    OddsEventRead,
    OddsEventsRead,
    OddsPreviewRead,
    ProviderQuotaRead,
    ProviderUsageRead,
    StatsApplyRead,
    StatsApplyRequest,
    StatsApplyResult,
    StatsCandidateRead,
    StatsPreviewRead,
    SyncCounts,
    SyncRunRead,
)
from app.services import connectors as service
from app.services.connectors import as_utc

router = APIRouter(
    prefix="/connectors",
    tags=["Connecteurs"],
    dependencies=[Depends(deps.get_auth_context), Depends(deps.verify_csrf)],
)


def _connector_error(exc: ConnectorError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _counts(run: Any) -> SyncCounts:
    return SyncCounts(**((run.summary or {}).get("counts") or {}))


def _preview_payload(run: Any) -> dict[str, Any]:
    summary = run.summary or {}
    return {
        "run_id": run.id,
        "provider": run.provider,
        "operation": run.operation,
        "status": run.status,
        "expires_at": run.expires_at,
        "quota": ProviderQuotaRead(
            used=0, remaining=run.quota_remaining, limit=None, reset_at=None
        ),
        "counts": _counts(run),
        "warnings": summary.get("warnings", []),
    }


def _link_or_404(db: Session, link_id: UUID) -> Any:
    try:
        return service.get_link(db, link_id)
    except LookupError as exc:
        not_found(str(exc))


@router.get("", response_model=ConnectorOverviewRead)
def overview(db: deps.DbSession) -> ConnectorOverviewRead:
    return ConnectorOverviewRead(
        providers=service.provider_statuses(db),
        usage=service.provider_usage(db),
        links=service.list_links(db),
    )


@router.get("/links", response_model=list[ConnectorLinkRead])
def list_links(db: deps.DbSession) -> list[ConnectorLinkRead]:
    return service.list_links(db)


@router.post("/links", response_model=ConnectorLinkRead, status_code=status.HTTP_201_CREATED)
def create_link(db: deps.DbSession, payload: ConnectorLinkCreate) -> ConnectorLinkRead:
    try:
        link = service.create_link(db, payload)
    except LookupError as exc:
        not_found(str(exc))
    commit_or_conflict(db, "Ce lien existe déjà pour ce fournisseur.")
    return link


@router.patch("/links/{link_id}", response_model=ConnectorLinkRead)
def update_link(
    db: deps.DbSession, link_id: UUID, payload: ConnectorLinkUpdate
) -> ConnectorLinkRead:
    link = _link_or_404(db, link_id)
    result = service.update_link(db, link, payload)
    commit_or_conflict(db, "Mise à jour du lien impossible.")
    return result


@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_link(db: deps.DbSession, link_id: UUID) -> None:
    link = _link_or_404(db, link_id)
    service.delete_link(db, link)
    commit_or_conflict(db, "Suppression du lien impossible.")


@router.get("/bigballsdata/leagues", response_model=list[DiscoveredCompetitionRead])
def bigballs_leagues(
    db: deps.DbSession, search: str | None = Query(default=None, max_length=120)
) -> list[DiscoveredCompetitionRead]:
    try:
        items = service.discover_bigballs_leagues(db, search)
        db.commit()
    except ConnectorError as exc:
        db.rollback()
        raise _connector_error(exc) from exc
    return [DiscoveredCompetitionRead(**item) for item in items]


@router.get("/the-odds-api/sports", response_model=list[DiscoveredCompetitionRead])
def odds_sports(db: deps.DbSession) -> list[DiscoveredCompetitionRead]:
    try:
        items = service.discover_competitions(db, "the_odds_api")
        db.commit()
    except ConnectorError as exc:
        db.rollback()
        raise _connector_error(exc) from exc
    return [DiscoveredCompetitionRead(**item) for item in items]


@router.get("/football-data/competitions", response_model=list[DiscoveredCompetitionRead])
def football_data_competitions(db: deps.DbSession) -> list[DiscoveredCompetitionRead]:
    try:
        items = service.discover_competitions(db, "football_data")
        db.commit()
    except ConnectorError as exc:
        db.rollback()
        raise _connector_error(exc) from exc
    return [DiscoveredCompetitionRead(**item) for item in items]


@router.post("/links/{link_id}/fixtures/preview", response_model=FixturesPreviewRead)
def preview_fixtures(db: deps.DbSession, link_id: UUID) -> FixturesPreviewRead:
    link = _link_or_404(db, link_id)
    try:
        run = service.preview_fixtures(db, link)
        db.commit()
    except ConnectorError as exc:
        db.rollback()
        raise _connector_error(exc) from exc
    summary = run.summary or {}
    return FixturesPreviewRead(
        **_preview_payload(run),
        teams_to_create=summary.get("teams_to_create", []),
        conflicts=summary.get("conflicts", []),
    )


@router.post("/links/{link_id}/stats/preview", response_model=StatsPreviewRead)
def preview_stats(db: deps.DbSession, link_id: UUID) -> StatsPreviewRead:
    link = _link_or_404(db, link_id)
    try:
        data = service.preview_stats(db, link)
    except ConnectorError as exc:
        raise _connector_error(exc) from exc
    candidates = [
        StatsCandidateRead(
            match_id=match.id,
            label=f"{match.home_team.name} — {match.away_team.name}",
            kickoff_at=as_utc(match.kickoff_at),
            status=match.status.value,
        )
        for match in data["candidates"]
    ]
    return StatsPreviewRead(
        provider=data["provider"],
        candidates=candidates,
        cost=data["cost"],
        budget_remaining=data["budget_remaining"],
    )


@router.post("/links/{link_id}/stats/apply", response_model=StatsApplyRead)
def apply_stats(
    db: deps.DbSession, link_id: UUID, payload: StatsApplyRequest
) -> StatsApplyRead:
    link = _link_or_404(db, link_id)
    try:
        result = service.apply_stats_batch(db, link, payload.match_ids)
        db.commit()
    except ConnectorError as exc:
        db.rollback()
        raise _connector_error(exc) from exc
    return StatsApplyRead(
        results=[StatsApplyResult(**item) for item in result["results"]],
        created=result["created"],
        conflicts=result["conflicts"],
        ignored=result["ignored"],
    )


@router.post("/links/{link_id}/odds/events", response_model=OddsEventsRead)
def odds_events(db: deps.DbSession, link_id: UUID) -> OddsEventsRead:
    link = _link_or_404(db, link_id)
    try:
        matched, unmatched = service.list_odds_events(db, link)
        db.commit()
    except ConnectorError as exc:
        db.rollback()
        raise _connector_error(exc) from exc
    return OddsEventsRead(
        matched=[OddsEventRead(**item) for item in matched],
        unmatched=[OddsEventRead(**item) for item in unmatched],
        bookmaker="1xBet",
    )


@router.post("/links/{link_id}/odds/preview", response_model=OddsPreviewRead)
def preview_odds(db: deps.DbSession, link_id: UUID) -> OddsPreviewRead:
    link = _link_or_404(db, link_id)
    try:
        run = service.preview_odds(db, link)
        db.commit()
    except ConnectorError as exc:
        db.rollback()
        raise _connector_error(exc) from exc
    return OddsPreviewRead(**_preview_payload(run), bookmaker="1xBet")


@router.post("/links/{link_id}/odds/extended/preview", response_model=OddsPreviewRead)
def preview_extended_odds(
    db: deps.DbSession, link_id: UUID, payload: ExtendedOddsRequest
) -> OddsPreviewRead:
    link = _link_or_404(db, link_id)
    try:
        run = service.preview_extended_odds(db, link, payload.match_ids)
        db.commit()
    except ConnectorError as exc:
        db.rollback()
        raise _connector_error(exc) from exc
    return OddsPreviewRead(**_preview_payload(run), bookmaker="1xBet")


@router.post("/sync-runs/{run_id}/apply", response_model=ApplyPreviewRead)
def apply_run(db: deps.DbSession, run_id: UUID) -> ApplyPreviewRead:
    try:
        run = service.get_run(db, run_id)
        counts = service.apply_preview(db, run)
        db.commit()
    except LookupError as exc:
        db.rollback()
        not_found(str(exc))
    except ConnectorError as exc:
        db.rollback()
        raise _connector_error(exc) from exc
    return ApplyPreviewRead(
        run_id=run.id,
        status=run.status,
        counts=SyncCounts(**counts.as_dict()),
    )


@router.post("/the-odds-api/events/{event_id}/link", status_code=status.HTTP_204_NO_CONTENT)
def link_event(
    db: deps.DbSession,
    event_id: str,
    payload: EventLinkRequest,
    link_id: Annotated[UUID, Query()],
) -> None:
    link = _link_or_404(db, link_id)
    try:
        service.link_event(db, link, event_id, payload.match_id)
    except LookupError as exc:
        not_found(str(exc))
    commit_or_conflict(db, "Association impossible.")


@router.get("/sync-runs", response_model=list[SyncRunRead])
def list_runs(
    db: deps.DbSession, limit: int = Query(default=20, ge=1, le=100)
) -> list[SyncRunRead]:
    return [SyncRunRead.model_validate(run) for run in service.list_runs(db, limit)]


@router.get("/provider-usage", response_model=list[ProviderUsageRead])
def provider_usage(db: deps.DbSession) -> list[ProviderUsageRead]:
    return service.provider_usage(db)
