"""Marchés, sélections et relevés de cotes."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.v1._helpers import conflict, not_found
from app.core import deps
from app.models.market import Market, MarketSubject, MarketTemplate
from app.models.match import Match
from app.schemas.market import (
    MarketCreate,
    MarketRead,
    MarketTemplateRead,
    MarketUpdate,
    OddsCreate,
    OddsRead,
)
from app.services import audit
from app.services import markets as market_service

router = APIRouter(
    tags=["Marchés et cotes"],
    dependencies=[Depends(deps.get_auth_context), Depends(deps.verify_csrf)],
)


def _load_match(db: deps.DbSession, match_id: UUID) -> Match:
    match = db.scalar(
        select(Match)
        .options(selectinload(Match.home_team), selectinload(Match.away_team))
        .where(Match.id == match_id)
    )
    if match is None:
        not_found("Rencontre introuvable.")
    return match


def _load_market(db: deps.DbSession, market_id: UUID) -> Market:
    market = market_service.load_market(db, market_id)
    if market is None:
        not_found("Marché introuvable.")
    return market


def _check_subject(match: Match, payload: MarketCreate) -> None:
    if payload.subject != MarketSubject.TEAM:
        return
    if payload.subject_team_id not in (match.home_team_id, match.away_team_id):
        conflict("L'équipe du marché doit être l'une des deux équipes de la rencontre.")


def _check_line(template: MarketTemplate | None, payload: MarketCreate) -> None:
    if template is None:
        return
    if template.line_kind in {"simple", "intervalle"} and payload.line is None:
        conflict("Ce marché nécessite une ligne (par exemple 2,5 buts).")
    if template.line_kind == "double" and (payload.line is None or payload.line2 is None):
        conflict("Ce marché nécessite deux lignes.")


@router.get(
    "/markets/catalog",
    response_model=list[MarketTemplateRead],
    summary="Catalogue des marchés disponibles",
)
def list_catalog(
    db: deps.DbSession,
    sport_code: str | None = None,
    family: str | None = None,
    include_inactive: bool = False,
) -> list[MarketTemplate]:
    conditions = []
    if sport_code:
        conditions.append(MarketTemplate.sport_code == sport_code)
    if family:
        conditions.append(MarketTemplate.family == family)
    if not include_inactive:
        conditions.append(MarketTemplate.is_active.is_(True))
    return list(
        db.scalars(
            select(MarketTemplate)
            .where(*conditions)
            .order_by(MarketTemplate.family, MarketTemplate.name)
        ).all()
    )


@router.get(
    "/matches/{match_id}/markets",
    response_model=list[MarketRead],
    summary="Marchés et cotes d'une rencontre",
)
def list_match_markets(match_id: UUID, db: deps.DbSession) -> list[MarketRead]:
    _load_match(db, match_id)
    return [
        market_service.to_market_read(m) for m in market_service.load_match_markets(db, match_id)
    ]


@router.post(
    "/matches/{match_id}/markets",
    response_model=MarketRead,
    status_code=status.HTTP_201_CREATED,
    summary="Ajouter un marché à une rencontre",
)
def create_market(
    match_id: UUID,
    payload: MarketCreate,
    db: deps.DbSession,
    user: deps.CurrentUser,
) -> MarketRead:
    match = _load_match(db, match_id)
    _check_subject(match, payload)
    template = market_service.resolve_template(db, payload.template_code)
    if payload.template_code and template is None:
        not_found("Modèle de marché introuvable dans le catalogue.")
    _check_line(template, payload)

    try:
        market = market_service.create_market(db, match, payload)
    except ValueError as exc:
        conflict(str(exc))
    except IntegrityError:
        db.rollback()
        conflict("Ce marché existe déjà pour cette rencontre.")

    audit.record(
        db,
        "market.create",
        user_id=user.id,
        entity="market",
        entity_id=str(market.id),
        payload={
            "match_id": str(match_id),
            "nom": market.name,
            "famille": market.family,
            "periode": market.period,
            "sujet": str(market.subject),
            "ligne": market.line,
            "selections": len(market.selections),
        },
    )
    return market_service.to_market_read(market)


@router.get("/markets/{market_id}", response_model=MarketRead, summary="Détail d'un marché")
def get_market(market_id: UUID, db: deps.DbSession) -> MarketRead:
    return market_service.to_market_read(_load_market(db, market_id))


@router.patch("/markets/{market_id}", response_model=MarketRead, summary="Modifier un marché")
def update_market(
    market_id: UUID,
    payload: MarketUpdate,
    db: deps.DbSession,
    user: deps.CurrentUser,
) -> MarketRead:
    market = _load_market(db, market_id)
    try:
        updated = market_service.update_market(db, market, payload)
    except IntegrityError:
        db.rollback()
        conflict("Un marché identique existe déjà pour cette rencontre.")
    audit.record(
        db,
        "market.update",
        user_id=user.id,
        entity="market",
        entity_id=str(market_id),
        payload=payload.model_dump(exclude_unset=True, mode="json"),
    )
    return market_service.to_market_read(updated)


@router.delete(
    "/markets/{market_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un marché et son historique",
)
def delete_market(market_id: UUID, db: deps.DbSession, user: deps.CurrentUser) -> None:
    market = _load_market(db, market_id)
    db.delete(market)
    db.commit()
    audit.record(db, "market.delete", user_id=user.id, entity="market", entity_id=str(market_id))


@router.get(
    "/markets/{market_id}/history",
    response_model=list[OddsRead],
    summary="Historique complet des cotes d'un marché",
)
def get_market_history(market_id: UUID, db: deps.DbSession) -> list[OddsRead]:
    return market_service.market_history(_load_market(db, market_id))


@router.post(
    "/markets/{market_id}/selections/{selection_id}/odds",
    response_model=MarketRead,
    status_code=status.HTTP_201_CREATED,
    summary="Ajouter un relevé de cote",
)
def add_odds(
    market_id: UUID,
    selection_id: UUID,
    payload: OddsCreate,
    db: deps.DbSession,
    user: deps.CurrentUser,
) -> MarketRead:
    market = _load_market(db, market_id)
    try:
        _, snapshot = market_service.add_odds(db, market, selection_id, payload)
    except LookupError as exc:
        not_found(str(exc))

    audit.record(
        db,
        "odds.create",
        user_id=user.id,
        entity="selection",
        entity_id=str(selection_id),
        payload={
            "marche": str(market_id),
            "cote": snapshot.decimal_odds,
            "bookmaker": snapshot.bookmaker,
            "source": snapshot.source,
            "captured_at": snapshot.captured_at.isoformat(),
        },
    )
    refreshed = _load_market(db, market_id)
    return market_service.to_market_read(refreshed)


@router.delete(
    "/markets/{market_id}/selections/{selection_id}/odds/{snapshot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un relevé de cote erroné",
)
def delete_odds(
    market_id: UUID,
    selection_id: UUID,
    snapshot_id: UUID,
    db: deps.DbSession,
    user: deps.CurrentUser,
) -> None:
    market = _load_market(db, market_id)
    try:
        snapshot = market_service.find_snapshot(market, selection_id, snapshot_id)
    except LookupError as exc:
        not_found(str(exc))
    db.delete(snapshot)
    db.commit()
    audit.record(
        db,
        "odds.delete",
        user_id=user.id,
        entity="odds_snapshot",
        entity_id=str(snapshot_id),
        payload={"marche": str(market_id), "selection": str(selection_id)},
    )
