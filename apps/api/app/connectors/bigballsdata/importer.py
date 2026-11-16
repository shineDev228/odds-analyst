"""Importateur BigBallsData : écriture directe dans les tables métier.

Il n'existe plus de table de correspondance : l'identifiant du fournisseur est
stocké dans ``teams.external_id`` et ``matches.external_id``. L'équipe en base
**est** l'équipe du fournisseur. Aucune comparaison de noms n'est utilisée pour
créer ou fusionner une entité.

Règles :

- une rencontre sans ``external_id`` (saisie manuelle) n'est jamais touchée ;
- une rencontre importée est mise à jour à chaque passe, champ par champ ;
- le xG n'est **jamais** écrit ici : il vient du CSV ;
- une valeur absente reste ``NULL``.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import (
    NormalizedMatch,
    NormalizedStanding,
    NormalizedTeam,
    NormalizedTeamStats,
)
from app.models.match import Match, MatchStatus, TeamMatchStats
from app.models.reference import Competition, Season, Sport, Team
from app.models.snapshot import StandingsSnapshot

PROVIDER = "bigballsdata"


class ImportConflict(Exception):
    """Un objet interne homonyme empêche l'écriture sans ambiguïté."""


@dataclass(slots=True)
class ImportCounts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    ignored: int = 0


def season_label(external_label: str) -> str:
    """« 2026 » devient « 2026-2027 » ; une année simple est une saison."""
    text = external_label.strip()
    if len(text) == 4 and text.isdigit():
        return f"{text}-{int(text) + 1}"
    return text


def get_football(db: Session) -> Sport:
    sport = db.scalar(select(Sport).where(Sport.code == "football"))
    if sport is None:
        raise ImportConflict(
            "Le sport « football » n'existe pas. La base n'est pas initialisée."
        )
    return sport


def upsert_competition(
    db: Session, *, sport_id: UUID, code: str, name: str, country: str | None
) -> Competition:
    competition = db.scalar(select(Competition).where(Competition.code == code))
    if competition is None:
        competition = db.scalar(
            select(Competition).where(
                Competition.code.is_(None),
                Competition.sport_id == sport_id,
                Competition.name == name,
            )
        )
        if competition is not None:
            competition.code = code
    if competition is None:
        competition = Competition(
            sport_id=sport_id,
            code=code,
            name=name,
            country=country,
            is_active=True,
        )
        db.add(competition)
        db.flush()
        return competition

    competition.name = name
    if country is not None:
        competition.country = country
    competition.is_active = True
    return competition


def upsert_season(db: Session, *, competition: Competition, external_label: str) -> Season:
    label = season_label(external_label)
    season = db.scalar(
        select(Season).where(
            Season.competition_id == competition.id,
            Season.label == label,
        )
    )
    if season is None:
        season = Season(
            competition_id=competition.id,
            label=label,
            external_label=external_label,
            is_current=True,
        )
        db.add(season)
        db.flush()
        return season
    season.external_label = external_label
    season.is_current = True
    return season


def upsert_team(db: Session, *, sport_id: UUID, team: NormalizedTeam) -> tuple[Team, bool]:
    """Retourne l'équipe et ``True`` si elle vient d'être créée."""
    row = db.scalar(select(Team).where(Team.external_id == team.external_id))
    if row is None:
        homonym = db.scalar(
            select(Team).where(
                Team.sport_id == sport_id,
                Team.name == team.name,
            )
        )
        if homonym is not None and homonym.external_id is None:
            # Reprise d'une équipe antérieure sans identifiant fournisseur.
            homonym.external_id = team.external_id
            row = homonym
        elif homonym is not None:
            raise ImportConflict(
                f"Deux équipes portent le nom « {team.name} » avec des identifiants "
                "fournisseur différents."
            )
        else:
            row = Team(
                sport_id=sport_id,
                external_id=team.external_id,
                name=team.name,
                short_name=team.short_name,
                logo_url=team.logo_url,
            )
            db.add(row)
            db.flush()
            return row, True

    row.name = team.name
    if team.short_name is not None:
        row.short_name = team.short_name
    if team.logo_url is not None:
        row.logo_url = team.logo_url
    return row, False


def upsert_match(
    db: Session,
    *,
    season: Season,
    match: NormalizedMatch,
    home: Team,
    away: Team,
    now: datetime,
) -> tuple[Match, str]:
    """Crée ou met à jour une rencontre ; retourne (rencontre, action)."""
    row = db.scalar(select(Match).where(Match.external_id == match.external_id))
    values = {
        "season_id": season.id,
        "home_team_id": home.id,
        "away_team_id": away.id,
        "kickoff_at": match.kickoff_at,
        "status": MatchStatus(match.status),
        "home_score": match.home_score,
        "away_score": match.away_score,
        "half_time_home_score": match.half_time_home_score,
        "half_time_away_score": match.half_time_away_score,
        "round_name": match.round_name,
        "broadcast": match.broadcast,
        "attendance": match.attendance,
        "has_odds": match.has_odds,
        "data_source": PROVIDER,
        "source_updated_at": now,
    }
    if row is None:
        row = Match(external_id=match.external_id, **values)
        db.add(row)
        db.flush()
        return row, "created"

    changed = False
    for field, value in values.items():
        # SQLite rend les dates sans fuseau : comparer en UTC évite une
        # réécriture factice à chaque passe.
        if _same_value(getattr(row, field), value):
            continue
        setattr(row, field, value)
        changed = True
    return row, ("updated" if changed else "unchanged")


def _same_value(current: object, value: object) -> bool:
    if isinstance(current, datetime) and isinstance(value, datetime):
        left = current if current.tzinfo else current.replace(tzinfo=UTC)
        right = value if value.tzinfo else value.replace(tzinfo=UTC)
        return left.astimezone(UTC) == right.astimezone(UTC)
    return current == value


STATS_COLUMNS = (
    "shots",
    "shots_on_target",
    "shots_off_target",
    "blocked_shots",
    "shots_inside_box",
    "shots_outside_box",
    "possession",
    "corners",
    "fouls",
    "offsides",
    "yellow_cards",
    "red_cards",
    "goalkeeper_saves",
    "passes",
    "accurate_passes",
    "pass_percentage",
)


def apply_statistics(
    db: Session,
    *,
    match: Match,
    lines: list[NormalizedTeamStats],
    teams: dict[str, Team],
) -> ImportCounts:
    """Écrit les statistiques d'une rencontre, sans jamais toucher au xG."""
    counts = ImportCounts()
    for line in lines:
        team = teams.get(line.team_external_id)
        if team is None:
            counts.ignored += 1
            continue
        row = db.scalar(
            select(TeamMatchStats).where(
                TeamMatchStats.match_id == match.id,
                TeamMatchStats.team_id == team.id,
            )
        )
        values = {column: getattr(line, column) for column in STATS_COLUMNS}
        if line.is_home:
            values["goals_for"] = match.home_score
            values["goals_against"] = match.away_score
        else:
            values["goals_for"] = match.away_score
            values["goals_against"] = match.home_score
        if row is None:
            db.add(
                TeamMatchStats(
                    match_id=match.id,
                    team_id=team.id,
                    is_home=line.is_home,
                    expected_goals=line.expected_goals,
                    data_source=PROVIDER,
                    **values,
                )
            )
            counts.created += 1
            continue
        changed = False
        for field, value in values.items():
            if getattr(row, field) != value:
                setattr(row, field, value)
                changed = True
        # Le xG appartient au CSV : une passe BigBallsData ne l'écrase jamais.
        if row.expected_goals is None and line.expected_goals is not None:
            row.expected_goals = line.expected_goals
            changed = True
        if changed:
            row.data_source = PROVIDER
            counts.updated += 1
        else:
            counts.unchanged += 1
    db.flush()
    return counts


def apply_standings(
    db: Session,
    *,
    competition: Competition,
    season: Season,
    lines: list[NormalizedStanding],
    teams: dict[str, Team],
    now: datetime | None = None,
) -> ImportCounts:
    """Écrit le classement du jour, une ligne par équipe et par journée."""
    counts = ImportCounts()
    day = (now or datetime.now(UTC)).astimezone(UTC).date()
    for line in lines:
        team = teams.get(line.team_external_id)
        if team is None:
            counts.ignored += 1
            continue
        row = db.scalar(
            select(StandingsSnapshot).where(
                StandingsSnapshot.team_id == team.id,
                StandingsSnapshot.season_id == season.id,
                StandingsSnapshot.captured_on == day,
            )
        )
        values = {
            "competition_id": competition.id,
            "rank": line.rank,
            "played": line.played,
            "wins": line.wins,
            "draws": line.draws,
            "losses": line.losses,
            "goals_for": line.goals_for,
            "goals_against": line.goals_against,
            "form_string": line.form_string,
        }
        if row is None:
            db.add(
                StandingsSnapshot(
                    team_id=team.id,
                    season_id=season.id,
                    captured_on=day,
                    **values,
                )
            )
            counts.created += 1
            continue
        changed = False
        for field, value in values.items():
            if getattr(row, field) != value:
                setattr(row, field, value)
                changed = True
        if changed:
            counts.updated += 1
        else:
            counts.unchanged += 1
    db.flush()
    return counts
