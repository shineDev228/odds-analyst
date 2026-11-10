"""Écriture commune aux connecteurs : équipes, rencontres, statistiques, cotes.

Les aperçus ne touchent jamais aux tables métier. Ils produisent un plan JSON
stocké dans `sync_runs`; l'application exécute ce plan sans aucun appel réseau.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import NormalizedTeam, PreviewCounts
from app.connectors.matching import kickoff_close, same_team
from app.models.connector import ProviderRef, RefEntity
from app.models.market import Market, MarketSubject, MarketTemplate, OddsSnapshot, Selection
from app.models.match import Match, MatchStatus, TeamMatchStats
from app.models.reference import Team
from app.services.markets import build_signature

MANUAL = "manual"


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return as_utc(value)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return as_utc(parsed)


def get_ref(db: Session, provider: str, entity_type: str, external_id: str) -> ProviderRef | None:
    return db.scalar(
        select(ProviderRef).where(
            ProviderRef.provider == provider,
            ProviderRef.entity_type == entity_type,
            ProviderRef.external_id == external_id,
        )
    )


def get_ref_for_entity(
    db: Session, provider: str, entity_type: str, entity_id: UUID
) -> ProviderRef | None:
    return db.scalar(
        select(ProviderRef).where(
            ProviderRef.provider == provider,
            ProviderRef.entity_type == entity_type,
            ProviderRef.entity_id == entity_id,
        )
    )


def link_ref(
    db: Session,
    provider: str,
    entity_type: RefEntity,
    entity_id: UUID,
    external_id: str,
    details: dict[str, Any] | None = None,
) -> ProviderRef:
    """Crée ou met à jour sans doublon la référence externe."""
    existing = get_ref(db, provider, entity_type.value, external_id)
    if existing is None:
        existing = ProviderRef(
            provider=provider,
            entity_type=entity_type.value,
            entity_id=entity_id,
            external_id=external_id,
            details=details,
        )
        db.add(existing)
    elif existing.entity_id != entity_id:
        existing.entity_id = entity_id
    db.flush()
    return existing


# ---------------------------------------------------------------------------
# Équipes
# ---------------------------------------------------------------------------


def resolve_team(
    db: Session, provider: str, team: NormalizedTeam, *, sport_id: UUID
) -> tuple[UUID | None, str]:
    """Associe une équipe par référence ou égalité stricte.

    Retourne `(identifiant, statut)` avec `statut` parmi `existing`, `missing`,
    `ambiguous`.
    """
    ref = get_ref(db, provider, RefEntity.TEAM.value, team.external_id)
    if ref is not None:
        return ref.entity_id, "existing"

    candidates = db.scalars(select(Team).where(Team.sport_id == sport_id)).all()
    matches = [
        candidate
        for candidate in candidates
        if same_team(team.name, team.short_name, candidate.name, candidate.short_name)
    ]
    if len(matches) == 1:
        link_ref(db, provider, RefEntity.TEAM, matches[0].id, team.external_id)
        return matches[0].id, "existing"
    if len(matches) > 1:
        return None, "ambiguous"
    return None, "missing"


def create_team(db: Session, provider: str, team: NormalizedTeam, *, sport_id: UUID) -> UUID:
    """Crée une équipe manquante puis enregistre sa référence externe."""
    existing = get_ref(db, provider, RefEntity.TEAM.value, team.external_id)
    if existing is not None:
        return existing.entity_id
    row = Team(sport_id=sport_id, name=team.name, short_name=team.short_name)
    db.add(row)
    db.flush()
    link_ref(db, provider, RefEntity.TEAM, row.id, team.external_id)
    return row.id


# ---------------------------------------------------------------------------
# Rencontres
# ---------------------------------------------------------------------------


def plan_matches(
    db: Session,
    *,
    provider: str,
    sport_id: UUID,
    season_id: UUID,
    matches: list[dict[str, Any]],
) -> tuple[dict[str, Any], PreviewCounts]:
    """Construit le plan de calendrier sans écrire dans les tables métier."""
    counts = PreviewCounts(received=len(matches))
    planned_teams: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []

    for raw in matches:
        item = dict(raw)
        item["conflicts"] = []
        statuses: list[str] = []
        for side in ("home", "away"):
            team = NormalizedTeam(
                external_id=str(raw[f"{side}_external_id"]),
                name=str(raw[f"{side}_name"]),
                short_name=raw.get(f"{side}_short_name"),
            )
            team_id, status = resolve_team(db, provider, team, sport_id=sport_id)
            statuses.append(status)
            if team_id is not None:
                item[f"{side}_team_id"] = str(team_id)
            else:
                item[f"{side}_team_id"] = None
                if status == "missing":
                    planned_teams.setdefault(
                        team.external_id,
                        {
                            "external_id": team.external_id,
                            "name": team.name,
                            "short_name": team.short_name,
                        },
                    )

        if "ambiguous" in statuses:
            item["action"] = "conflict"
            item["conflicts"].append(
                "Plusieurs équipes internes correspondent ; aucune fusion automatique."
            )
            counts.conflicts += 1
            items.append(item)
            continue

        existing = _find_match(db, provider, item)
        if existing is None:
            item["action"] = "create"
            item["match_id"] = None
            counts.created += 1
        else:
            item["match_id"] = str(existing.id)
            decision, conflicts = _merge_decision(existing, item)
            item["action"] = decision
            item["conflicts"].extend(conflicts)
            if decision == "update":
                counts.updated += 1
            elif decision == "conflict":
                counts.conflicts += 1
            else:
                counts.unchanged += 1
        items.append(item)

    plan = {
        "provider": provider,
        "sport_id": str(sport_id),
        "season_id": str(season_id),
        "teams": list(planned_teams.values()),
        "matches": items,
    }
    return plan, counts


def _find_match(db: Session, provider: str, item: dict[str, Any]) -> Match | None:
    ref = get_ref(db, provider, RefEntity.MATCH.value, str(item["external_id"]))
    if ref is not None:
        return db.get(Match, ref.entity_id)

    home_id = item.get("home_team_id")
    away_id = item.get("away_team_id")
    if not home_id or not away_id:
        return None
    kickoff = _parse_dt(item["kickoff_at"])
    candidates = db.scalars(
        select(Match).where(
            Match.season_id == UUID(str(item["season_id"])),
            Match.home_team_id == UUID(str(home_id)),
            Match.away_team_id == UUID(str(away_id)),
        )
    ).all()
    for candidate in candidates:
        if kickoff_close(as_utc(candidate.kickoff_at), kickoff):
            return candidate
    return None


def _merge_decision(existing: Match, item: dict[str, Any]) -> tuple[str, list[str]]:
    """Décide quoi faire d'une rencontre existante, sans écrire."""
    conflicts: list[str] = []
    if existing.data_source == MANUAL:
        for field, incoming in (
            ("home_score", item.get("home_score")),
            ("away_score", item.get("away_score")),
            ("kickoff_at", item.get("kickoff_at")),
            ("status", item.get("status")),
        ):
            current = getattr(existing, field)
            if field == "kickoff_at":
                current = as_utc(current).isoformat() if current else None
                incoming = as_utc(_parse_dt(incoming)).isoformat() if incoming else None
            if current is not None and incoming is not None and str(current) != str(incoming):
                conflicts.append(f"Valeur manuelle conservée pour {field}.")
        return ("conflict" if conflicts else "unchanged"), conflicts

    changed = (
        existing.home_score != item.get("home_score")
        or existing.away_score != item.get("away_score")
        or as_utc(existing.kickoff_at) != _parse_dt(item["kickoff_at"])
        or existing.status.value != item.get("status")
    )
    return ("update" if changed else "unchanged"), conflicts


def apply_matches(db: Session, plan: dict[str, Any]) -> PreviewCounts:
    """Applique un plan de calendrier validé."""
    provider = str(plan["provider"])
    sport_id = UUID(str(plan["sport_id"]))
    season_id = UUID(str(plan["season_id"]))
    counts = PreviewCounts(received=len(plan.get("matches", [])))

    for team in plan.get("teams", []):
        create_team(
            db,
            provider,
            NormalizedTeam(
                external_id=str(team["external_id"]),
                name=str(team["name"]),
                short_name=team.get("short_name"),
            ),
            sport_id=sport_id,
        )

    for item in plan.get("matches", []):
        action = item.get("action")
        if action in {"conflict"}:
            counts.conflicts += 1
            continue
        home_id = item.get("home_team_id")
        away_id = item.get("away_team_id")
        if home_id is None:
            ref = get_ref(db, provider, RefEntity.TEAM.value, str(item["home_external_id"]))
            home_id = str(ref.entity_id) if ref else None
        if away_id is None:
            ref = get_ref(db, provider, RefEntity.TEAM.value, str(item["away_external_id"]))
            away_id = str(ref.entity_id) if ref else None
        if not home_id or not away_id:
            counts.ignored += 1
            continue

        match = db.get(Match, UUID(str(item["match_id"]))) if item.get("match_id") else None
        if match is None:
            match = Match(
                season_id=season_id,
                home_team_id=UUID(str(home_id)),
                away_team_id=UUID(str(away_id)),
                kickoff_at=_parse_dt(item["kickoff_at"]),
                status=MatchStatus(str(item["status"])),
                home_score=item.get("home_score"),
                away_score=item.get("away_score"),
                half_time_home_score=item.get("half_time_home_score"),
                half_time_away_score=item.get("half_time_away_score"),
                venue=item.get("venue"),
                data_source=provider,
                source_updated_at=datetime.now(UTC),
            )
            db.add(match)
            db.flush()
            link_ref(db, provider, RefEntity.MATCH, match.id, str(item["external_id"]))
            counts.created += 1
            continue

        link_ref(db, provider, RefEntity.MATCH, match.id, str(item["external_id"]))
        if action != "update":
            counts.unchanged += 1
            continue

        if match.data_source == MANUAL:
            # Une rencontre manuelle n'est jamais écrasée : seuls les champs
            # vides sont complétés.
            if match.home_score is None:
                match.home_score = item.get("home_score")
            if match.away_score is None:
                match.away_score = item.get("away_score")
            if match.half_time_home_score is None:
                match.half_time_home_score = item.get("half_time_home_score")
            if match.half_time_away_score is None:
                match.half_time_away_score = item.get("half_time_away_score")
            if not match.venue:
                match.venue = item.get("venue")
            counts.conflicts += 1
            continue

        match.kickoff_at = _parse_dt(item["kickoff_at"])
        match.status = MatchStatus(str(item["status"]))
        match.home_score = item.get("home_score")
        match.away_score = item.get("away_score")
        match.half_time_home_score = item.get("half_time_home_score")
        match.half_time_away_score = item.get("half_time_away_score")
        match.venue = item.get("venue") or match.venue
        match.data_source = provider
        match.source_updated_at = datetime.now(UTC)
        counts.updated += 1

    return counts


# ---------------------------------------------------------------------------
# Statistiques
# ---------------------------------------------------------------------------


def plan_stats(
    db: Session, *, provider: str, items: list[dict[str, Any]]
) -> tuple[dict[str, Any], PreviewCounts]:
    """Prépare l'écriture des statistiques d'équipe déjà récupérées."""
    counts = PreviewCounts(received=len(items))
    planned: list[dict[str, Any]] = []
    for item in items:
        match_id = str(item["match_id"])
        existing = db.scalar(
            select(TeamMatchStats).where(TeamMatchStats.match_id == UUID(match_id)).limit(1)
        )
        if existing is not None:
            planned.append({**item, "action": "conflict"})
            counts.conflicts += 1
            continue
        planned.append({**item, "action": "create"})
        counts.created += 1
    return {"provider": provider, "items": planned}, counts


def apply_stats(db: Session, plan: dict[str, Any]) -> PreviewCounts:
    provider = str(plan["provider"])
    counts = PreviewCounts(received=len(plan.get("items", [])))
    for item in plan.get("items", []):
        if item.get("action") != "create":
            counts.conflicts += 1
            continue
        match_id = UUID(str(item["match_id"]))
        written = False
        for row in item.get("stats", []):
            team_id = row.get("team_id")
            if not team_id:
                ref = get_ref(db, provider, RefEntity.TEAM.value, str(row["team_external_id"]))
                team_id = str(ref.entity_id) if ref else None
            if not team_id:
                continue
            db.add(
                TeamMatchStats(
                    match_id=match_id,
                    team_id=UUID(str(team_id)),
                    is_home=bool(row["is_home"]),
                    goals_for=row.get("goals_for"),
                    goals_against=row.get("goals_against"),
                    shots=row.get("shots"),
                    shots_on_target=row.get("shots_on_target"),
                    possession=row.get("possession"),
                    corners=row.get("corners"),
                    yellow_cards=row.get("yellow_cards"),
                    red_cards=row.get("red_cards"),
                    expected_goals=row.get("expected_goals"),
                    extra=row.get("extra"),
                    data_source=provider,
                )
            )
            written = True
        if written:
            counts.created += 1
        else:
            counts.ignored += 1
    db.flush()
    return counts


# ---------------------------------------------------------------------------
# Cotes
# ---------------------------------------------------------------------------


def _template(db: Session, code: str) -> MarketTemplate:
    template = db.scalar(select(MarketTemplate).where(MarketTemplate.code == code))
    if template is None:
        raise LookupError(f"Modèle de marché absent du catalogue : {code}")
    return template


def plan_odds(
    db: Session, *, provider: str, items: list[dict[str, Any]]
) -> tuple[dict[str, Any], PreviewCounts]:
    """Vérifie les marchés cibles sans écrire de cote."""
    counts = PreviewCounts(received=len(items))
    planned: list[dict[str, Any]] = []
    for item in items:
        match = db.get(Match, UUID(str(item["match_id"])))
        if match is None:
            counts.ignored += 1
            continue
        markets = []
        for market in item.get("markets", []):
            try:
                template = _template(db, str(market["template_code"]))
            except LookupError:
                counts.ignored += 1
                continue
            signature = build_signature(
                template_code=template.code,
                name=template.name,
                family=template.family,
                period=template.period,
                subject=template.subject,
                subject_team_id=None,
                subject_player=None,
                line=market.get("line"),
                line2=None,
            )
            existing = db.scalar(
                select(Market).where(
                    Market.match_id == match.id, Market.signature == signature
                )
            )
            markets.append(
                {
                    **market,
                    "signature": signature,
                    "market_id": str(existing.id) if existing else None,
                }
            )
            if existing is None:
                counts.created += 1
            else:
                counts.updated += 1
        planned.append({**item, "markets": markets})
    return {"provider": provider, "items": planned}, counts


def apply_odds(db: Session, plan: dict[str, Any]) -> PreviewCounts:
    provider = str(plan["provider"])
    counts = PreviewCounts(received=len(plan.get("items", [])))
    for item in plan.get("items", []):
        match_id = UUID(str(item["match_id"]))
        captured_at = _parse_dt(item["captured_at"])
        for market in item.get("markets", []):
            template = _template(db, str(market["template_code"]))
            market_id = market.get("market_id")
            if market_id:
                row = db.get(Market, UUID(str(market_id)))
            else:
                row = Market(
                    match_id=match_id,
                    template_code=template.code,
                    name=template.name,
                    family=template.family,
                    period=template.period,
                    subject=MarketSubject(template.subject),
                    line=market.get("line"),
                    signature=str(market["signature"]),
                    is_custom=False,
                )
                for index, spec in enumerate(template.selection_templates):
                    row.selections.append(
                        Selection(
                            code=str(spec["code"]),
                            label=str(spec["label"]),
                            sort_order=index,
                        )
                    )
                db.add(row)
                db.flush()
            if row is None:
                counts.ignored += 1
                continue
            selections = {selection.code: selection for selection in row.selections}
            added = 0
            for code, price in market.get("outcomes", {}).items():
                selection = selections.get(str(code))
                if selection is None:
                    counts.conflicts += 1
                    continue
                exists = db.scalar(
                    select(OddsSnapshot.id).where(
                        OddsSnapshot.selection_id == selection.id,
                        OddsSnapshot.source == provider,
                        OddsSnapshot.captured_at == captured_at,
                    )
                )
                if exists is not None:
                    counts.unchanged += 1
                    continue
                db.add(
                    OddsSnapshot(
                        selection_id=selection.id,
                        decimal_odds=float(price),
                        captured_at=captured_at,
                        bookmaker=str(item.get("bookmaker") or "1xBet"),
                        source=provider,
                    )
                )
                added += 1
            if added:
                counts.updated += 1
    db.flush()
    return counts
