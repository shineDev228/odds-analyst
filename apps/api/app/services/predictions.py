"""Service de prédiction : chargement de l'historique et sérialisation."""

from datetime import UTC, datetime
from uuid import UUID

from engine.prediction import (
    MODEL_VERSION,
    Estimate,
    FootballPrediction,
    predict_football,
)
from engine.ratings import (
    HistoricalMatch,
    InsufficientDataError,
    RatingConfig,
    TeamRating,
)
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import as_utc
from app.models.match import Match, MatchStatus
from app.models.reference import Competition, Season
from app.schemas.prediction import (
    PredictionQuality,
    PredictionRead,
    PredictionScoreline,
    PredictionSelection,
    PredictionSource,
    PredictionSources,
    PredictionTotal,
)
from app.services.preferences import get_preferences

AVERTISSEMENT = (
    "Probabilités estimées par un modèle statistique : elles ne garantissent "
    "aucun résultat et ne constituent pas un conseil de pari."
)

QUALITY_LABELS = {
    "tres_faible": "Très faible",
    "faible": "Faible",
    "moyenne": "Moyenne",
    "correcte": "Correcte",
    "bonne": "Bonne",
}

_MATCH_LOAD = (
    selectinload(Match.home_team),
    selectinload(Match.away_team),
    selectinload(Match.season).selectinload(Season.competition).selectinload(Competition.sport),
)


class InsufficientHistoryError(ValueError):
    """L'historique ne permet pas une estimation honnête."""


def _load_match(db: Session, match_id: UUID) -> Match:
    match = db.scalar(select(Match).options(*_MATCH_LOAD).where(Match.id == match_id))
    if match is None:
        raise LookupError("Rencontre introuvable.")
    return match


def _season_ids_for_sport(sport_id: UUID):
    return (
        select(Season.id)
        .join(Competition, Season.competition_id == Competition.id)
        .where(Competition.sport_id == sport_id)
    )


def _team_history(
    db: Session,
    team_id: UUID,
    sport_id: UUID,
    before: datetime,
    limit: int,
) -> list[Match]:
    return list(
        db.scalars(
            select(Match)
            .options(selectinload(Match.season), selectinload(Match.stats))
            .where(
                Match.status == MatchStatus.TERMINE,
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
                Match.kickoff_at < before,
                Match.season_id.in_(_season_ids_for_sport(sport_id)),
                or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
            )
            .order_by(Match.kickoff_at.desc())
            .limit(limit)
        ).all()
    )


def _league_history(db: Session, sport_id: UUID, before: datetime, limit: int = 400) -> list[Match]:
    return list(
        db.scalars(
            select(Match)
            .options(selectinload(Match.stats))
            .where(
                Match.status == MatchStatus.TERMINE,
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
                Match.kickoff_at < before,
                Match.season_id.in_(_season_ids_for_sport(sport_id)),
            )
            .order_by(Match.kickoff_at.desc())
            .limit(limit)
        ).all()
    )


def _stats_for(match: Match, team_id: UUID):
    for stats in match.stats:
        if stats.team_id == team_id:
            return stats
    return None


def to_historical(match: Match) -> HistoricalMatch:
    home_stats = _stats_for(match, match.home_team_id)
    away_stats = _stats_for(match, match.away_team_id)
    return HistoricalMatch(
        home_team_id=str(match.home_team_id),
        away_team_id=str(match.away_team_id),
        home_goals=int(match.home_score or 0),
        away_goals=int(match.away_score or 0),
        played_at=as_utc(match.kickoff_at),
        home_expected_goals=home_stats.expected_goals if home_stats else None,
        away_expected_goals=away_stats.expected_goals if away_stats else None,
        home_shots_on_target=home_stats.shots_on_target if home_stats else None,
        away_shots_on_target=away_stats.shots_on_target if away_stats else None,
    )


def _selection(estimate: Estimate, label: str) -> PredictionSelection:
    return PredictionSelection(
        code=estimate.code,
        label=label,
        probability=estimate.probability,
        low=estimate.low,
        high=estimate.high,
    )


def _format_line(line: float) -> str:
    return f"{line:g}".replace(".", ",")


def _warnings(
    prediction: FootballPrediction,
    history: list[Match],
    home_name: str,
    away_name: str,
    computed_at: datetime,
) -> list[str]:
    warnings: list[str] = []
    quality = prediction.quality
    if quality.effective_matches < 10:
        effective = f"{quality.effective_matches:.1f}".replace(".", ",")
        warnings.append(
            "Échantillon effectif faible "
            f"({effective} matchs pondérés) : la fourchette est élargie."
        )

    for rating, name in (
        (prediction.ratings.home, home_name),
        (prediction.ratings.away, away_name),
    ):
        if rating.matches < 5:
            warnings.append(f"{name} : seulement {rating.matches} matchs terminés pris en compte.")
        if rating.last_played_at is not None:
            days = (computed_at - rating.last_played_at).days
            if days > 90:
                warnings.append(f"{name} : le dernier match pris en compte date de {days} jours.")

    competition_ids = {match.season.competition_id for match in history if match.season}
    if len(competition_ids) > 1:
        warnings.append(
            "L'historique regroupe plusieurs compétitions : les niveaux d'opposition "
            "peuvent différer."
        )

    for rating, name in (
        (prediction.ratings.home, home_name),
        (prediction.ratings.away, away_name),
    ):
        coverage = rating.xg_coverage
        percentage = f"{coverage * 100:.0f}".replace(".", ",")
        if coverage <= 0.0:
            warnings.append(
                f"{name} : aucune statistique xG ni tir cadré ; estimation fondée sur les buts."
            )
        elif coverage < 0.5:
            warnings.append(
                f"{name} : xG ou tirs cadrés disponibles sur {percentage} % des matchs "
                "pondérés ; le modèle s'appuie surtout sur les buts."
            )

    warnings.append(
        "Modèle v2 : résultats complétés par le xG saisi ou, à défaut, par un proxy de "
        "tirs cadrés. Il ignore encore les compositions, les blessures et l'enjeu du match."
    )
    return warnings


def _source(rating: TeamRating) -> PredictionSource:
    return PredictionSource(
        matches=rating.matches,
        xg_matches=rating.xg_matches,
        proxy_matches=rating.proxy_matches,
        goals_only_matches=rating.goals_only_matches,
        xg_coverage=rating.xg_coverage,
        method=rating.statistics_method,
    )


def build_prediction(db: Session, match_id: UUID) -> PredictionRead:
    """Charge l'historique et produit l'analyse statistique complète."""
    match = _load_match(db, match_id)
    preferences = get_preferences(db)
    before = as_utc(match.kickoff_at)
    sport_id = match.season.competition.sport_id

    home_history = _team_history(
        db, match.home_team_id, sport_id, before, preferences.nb_matchs_historique
    )
    away_history = _team_history(
        db, match.away_team_id, sport_id, before, preferences.nb_matchs_historique
    )
    league = _league_history(db, sport_id, before)

    merged: dict[UUID, Match] = {item.id: item for item in home_history}
    merged.update({item.id: item for item in away_history})
    history = list(merged.values())

    config = RatingConfig(
        half_life_days=float(preferences.demi_vie_jours),
        max_matches_per_team=preferences.nb_matchs_historique,
    )

    try:
        prediction = predict_football(
            [to_historical(item) for item in history],
            league_matches=[to_historical(item) for item in league],
            home_team_id=str(match.home_team_id),
            away_team_id=str(match.away_team_id),
            as_of=before,
            config=config,
        )
    except InsufficientDataError as exc:
        raise InsufficientHistoryError(
            "Historique insuffisant : "
            f"{match.home_team.name} compte {exc.home_matches} match(s) terminé(s), "
            f"{match.away_team.name} en compte {exc.away_matches}. "
            f"Le modèle v2 exige au moins {exc.required} matchs terminés par équipe "
            "avant cette rencontre."
        ) from exc

    computed_at = datetime.now(UTC)
    quality = prediction.quality
    labels = {
        "1": "Domicile",
        "X": "Match nul",
        "2": "Extérieur",
    }
    double_chance_labels = {
        "1X": "Domicile ou nul",
        "12": "Domicile ou extérieur",
        "X2": "Nul ou extérieur",
    }
    btts_labels = {"oui": "Oui", "non": "Non"}

    return PredictionRead(
        match_id=match.id,
        model_version=MODEL_VERSION,
        computed_at=computed_at,
        expected_goals_home=prediction.expected_goals_home,
        expected_goals_away=prediction.expected_goals_away,
        expected_goals_total=prediction.expected_goals_home + prediction.expected_goals_away,
        quality=PredictionQuality(
            level=quality.level,
            label=QUALITY_LABELS.get(quality.level, quality.level),
            matches_home=quality.matches_home,
            matches_away=quality.matches_away,
            effective_home=prediction.ratings.home.effective_matches,
            effective_away=prediction.ratings.away.effective_matches,
            warnings=_warnings(
                prediction,
                history,
                match.home_team.name,
                match.away_team.name,
                computed_at,
            ),
        ),
        sources=PredictionSources(
            home=_source(prediction.ratings.home),
            away=_source(prediction.ratings.away),
        ),
        resultat=[
            _selection(item, labels.get(item.code, item.code)) for item in prediction.resultat
        ],
        double_chance=[
            _selection(item, double_chance_labels.get(item.code, item.code))
            for item in prediction.double_chance
        ],
        totaux=[
            PredictionTotal(
                line=total.line,
                over=_selection(total.over, f"Plus de {_format_line(total.line)} buts"),
                under=_selection(total.under, f"Moins de {_format_line(total.line)} buts"),
            )
            for total in prediction.totaux
        ],
        btts=[_selection(item, btts_labels.get(item.code, item.code)) for item in prediction.btts],
        scores_exacts=[
            PredictionScoreline(
                label=f"{score.home_goals}-{score.away_goals}",
                home_goals=score.home_goals,
                away_goals=score.away_goals,
                probability=score.probability,
            )
            for score in prediction.scores_exacts
        ],
        config={
            "demi_vie_jours": config.half_life_days,
            "nb_matchs_historique": config.max_matches_per_team,
            "simulations": config.simulations,
            "max_goals": config.max_goals,
            "dixon_coles_rho": prediction.ratings.dixon_coles_rho,
            "rho_prior": config.dixon_coles_rho,
            "xg_weight": config.xg_weight,
            "version": MODEL_VERSION,
        },
        avertissement=AVERTISSEMENT,
    )
