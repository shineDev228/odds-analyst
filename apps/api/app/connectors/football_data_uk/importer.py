"""Importateur football-data.co.uk : plan d'écriture puis application.

Le fournisseur ne fournit ni calendrier ni identifiant de rencontre : les lignes
sont rapprochées du calendrier interne par les équipes et par la date, jamais par
l'heure (le fichier est en heure locale sans fuseau).
"""

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import PreviewCounts
from app.connectors.football_data_uk.aliases import canonical_name, team_key
from app.connectors.football_data_uk.mapping import CsvRow
from app.connectors.import_common import as_utc, get_ref, link_ref
from app.connectors.matching import normalize_name, similar_teams
from app.models.connector import RefEntity
from app.models.match import Match, MatchStatus, TeamMatchStats
from app.models.reference import Team

MANUAL = "manual"


def _tokens(value: str) -> frozenset[str]:
    return frozenset(normalize_name(value).split())


def resolve_team(
    db: Session,
    provider: str,
    raw_name: str,
    *,
    sport_id: UUID,
) -> tuple[UUID | None, str, list[str]]:
    """Associe un nom du CSV à une équipe interne, sans jamais en créer.

    Retourne `(identifiant, statut, suggestions)` avec `statut` parmi
    `existing`, `ambiguous` et `missing`.
    """
    cle = team_key(raw_name)
    ref = get_ref(db, provider, RefEntity.TEAM.value, cle)
    if ref is not None:
        return ref.entity_id, "existing", []

    equipes = list(db.scalars(select(Team).where(Team.sport_id == sport_id)).all())
    jetons = _tokens(canonical_name(raw_name))
    candidats = [
        equipe
        for equipe in equipes
        if _tokens(equipe.name) == jetons
        or (equipe.short_name is not None and _tokens(equipe.short_name) == jetons)
    ]
    if len(candidats) == 1:
        link_ref(db, provider, RefEntity.TEAM, candidats[0].id, cle)
        return candidats[0].id, "existing", []
    if len(candidats) > 1:
        return None, "ambiguous", [equipe.name for equipe in candidats]

    suggestions = similar_teams(
        raw_name,
        [(str(equipe.id), equipe.name, equipe.short_name) for equipe in equipes],
        threshold=0.5,
    )
    noms = {str(equipe.id): equipe.name for equipe in equipes}
    return None, "missing", [noms[ident] for ident, _ in suggestions[:3]]


def _find_match(
    db: Session,
    *,
    season_id: UUID,
    home_id: UUID,
    away_id: UUID,
    played_on: date,
) -> Match | None:
    """Retrouve la rencontre du calendrier à ±1 jour autour de la date du fichier."""
    candidats = list(
        db.scalars(
            select(Match).where(
                Match.season_id == season_id,
                Match.home_team_id == home_id,
                Match.away_team_id == away_id,
            )
        ).all()
    )
    if not candidats:
        return None
    ecarts = sorted(
        ((abs((as_utc(item.kickoff_at).date() - played_on).days), item) for item in candidats),
        key=lambda paire: paire[0],
    )
    if ecarts[0][0] > 1:
        return None
    if len(ecarts) > 1 and ecarts[1][0] == ecarts[0][0]:
        return None
    return ecarts[0][1]


def _has_stats(db: Session, match_id: UUID) -> bool:
    return (
        db.scalar(
            select(TeamMatchStats.id).where(TeamMatchStats.match_id == match_id).limit(1)
        )
        is not None
    )


def _result_action(match: Match, row: CsvRow) -> str:
    """Décide du sort du résultat : `update`, `unchanged` ou `conflict`.

    Une rencontre manuelle conserve son score, mais son statut suit le fichier :
    un score final implique une rencontre terminée, jamais « programmée ».
    """
    if match.data_source == MANUAL:
        if match.home_score is None and match.away_score is None:
            return "update"
        if (match.home_score, match.away_score) != (row.home_score, row.away_score):
            return "conflict"
        return "unchanged" if match.status == MatchStatus.TERMINE else "update"
    if (
        (match.home_score, match.away_score) == (row.home_score, row.away_score)
        and (match.half_time_home_score, match.half_time_away_score)
        == (row.half_time_home, row.half_time_away)
        and match.status == MatchStatus.TERMINE
    ):
        return "unchanged"
    return "update"


def _row_stats(row: CsvRow, *, home_id: UUID, away_id: UUID) -> list[dict[str, Any]]:
    lignes: list[dict[str, Any]] = []
    for stats, team_id in ((row.home_stats, home_id), (row.away_stats, away_id)):
        lignes.append({"team_id": str(team_id), **stats.as_dict()})
    return lignes


def plan_import(
    db: Session,
    *,
    provider: str,
    season_id: UUID,
    sport_id: UUID,
    rows: list[CsvRow],
) -> tuple[dict[str, Any], PreviewCounts, list[dict[str, Any]]]:
    """Construit le plan « résultats + statistiques » sans écrire de données métier."""
    counts = PreviewCounts(received=len(rows))
    skipped: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []

    for row in rows:
        home_id, home_status, home_suggestions = resolve_team(
            db, provider, row.home_name, sport_id=sport_id
        )
        away_id, away_status, away_suggestions = resolve_team(
            db, provider, row.away_name, sport_id=sport_id
        )
        if home_id is None or away_id is None:
            counts.conflicts += 1
            skipped.append(
                {
                    "label": row.label,
                    "played_on": row.played_on.isoformat(),
                    "reason": "Équipe non reconnue",
                    "teams": [
                        {
                            "external_id": team_key(row.home_name),
                            "csv_name": row.home_name,
                            "status": home_status,
                            "suggestions": home_suggestions,
                        },
                        {
                            "external_id": team_key(row.away_name),
                            "csv_name": row.away_name,
                            "status": away_status,
                            "suggestions": away_suggestions,
                        },
                    ],
                }
            )
            continue

        match = _find_match(
            db,
            season_id=season_id,
            home_id=home_id,
            away_id=away_id,
            played_on=row.played_on,
        )
        if match is None:
            counts.ignored += 1
            skipped.append(
                {
                    "label": row.label,
                    "played_on": row.played_on.isoformat(),
                    "reason": "Rencontre absente du calendrier interne",
                    "teams": [],
                }
            )
            continue

        result_action = _result_action(match, row)
        stats_action = "conflict" if _has_stats(db, match.id) else "create"
        conflit = result_action == "conflict" or stats_action == "conflict"
        if result_action == "update":
            counts.updated += 1
        if stats_action == "create":
            counts.created += 1
        if conflit:
            counts.conflicts += 1
        if not (result_action == "update" or stats_action == "create" or conflit):
            counts.unchanged += 1

        items.append(
            {
                "match_id": str(match.id),
                "label": row.label,
                "played_on": row.played_on.isoformat(),
                "home_score": row.home_score,
                "away_score": row.away_score,
                "half_time_home_score": row.half_time_home,
                "half_time_away_score": row.half_time_away,
                "result_action": result_action,
                "stats_action": stats_action,
                "stats": _row_stats(row, home_id=home_id, away_id=away_id),
            }
        )

    plan = {
        "provider": provider,
        "season_id": str(season_id),
        "items": items,
    }
    return plan, counts, skipped


def apply_import(db: Session, plan: dict[str, Any]) -> PreviewCounts:
    """Applique le plan : résultats sans écraser le manuel, statistiques une seule fois."""
    provider = str(plan["provider"])
    items = plan.get("items", [])
    counts = PreviewCounts(received=len(items))
    maintenant = datetime.now(UTC)

    for item in items:
        match = db.get(Match, UUID(str(item["match_id"])))
        if match is None:
            counts.ignored += 1
            continue

        conflit = False
        resultat_ecrit = False
        if match.data_source == MANUAL:
            if match.home_score is None and match.away_score is None:
                match.home_score = item["home_score"]
                match.away_score = item["away_score"]
                if match.half_time_home_score is None:
                    match.half_time_home_score = item["half_time_home_score"]
                if match.half_time_away_score is None:
                    match.half_time_away_score = item["half_time_away_score"]
                match.status = MatchStatus.TERMINE
                resultat_ecrit = True
            elif (match.home_score, match.away_score) != (
                item["home_score"],
                item["away_score"],
            ):
                conflit = True
            elif match.status != MatchStatus.TERMINE:
                # Score manuel conservé, statut aligné sur le fichier.
                match.status = MatchStatus.TERMINE
                resultat_ecrit = True
        elif (
            (match.home_score, match.away_score)
            != (item["home_score"], item["away_score"])
            or (match.half_time_home_score, match.half_time_away_score)
            != (item["half_time_home_score"], item["half_time_away_score"])
            or match.status != MatchStatus.TERMINE
        ):
            match.home_score = item["home_score"]
            match.away_score = item["away_score"]
            match.half_time_home_score = item["half_time_home_score"]
            match.half_time_away_score = item["half_time_away_score"]
            match.status = MatchStatus.TERMINE
            match.data_source = provider
            match.source_updated_at = maintenant
            resultat_ecrit = True

        stats_ecrites = False
        if item.get("stats"):
            if _has_stats(db, match.id):
                conflit = True
            else:
                for ligne in item["stats"]:
                    db.add(
                        TeamMatchStats(
                            match_id=match.id,
                            team_id=UUID(str(ligne["team_id"])),
                            is_home=bool(ligne["is_home"]),
                            goals_for=ligne.get("goals_for"),
                            goals_against=ligne.get("goals_against"),
                            shots=ligne.get("shots"),
                            shots_on_target=ligne.get("shots_on_target"),
                            possession=ligne.get("possession"),
                            corners=ligne.get("corners"),
                            yellow_cards=ligne.get("yellow_cards"),
                            red_cards=ligne.get("red_cards"),
                            expected_goals=ligne.get("expected_goals"),
                            extra=ligne.get("extra"),
                            data_source=provider,
                        )
                    )
                stats_ecrites = True

        if resultat_ecrit:
            counts.updated += 1
        if stats_ecrites:
            counts.created += 1
        if conflit:
            counts.conflicts += 1
        if not (resultat_ecrit or stats_ecrites or conflit):
            counts.unchanged += 1

    db.flush()
    return counts


__all__ = ["apply_import", "plan_import", "resolve_team"]
