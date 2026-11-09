"""Service du rétro-test de calibration du moteur football.

Chaque rencontre évaluée est pronostiquée avec l'historique strictement
antérieur à son coup d'envoi, puis comparée à son résultat réel. Aucune
probabilité n'est stockée : le calcul est refait à la demande.
"""

from datetime import UTC, datetime

from engine.calibration import CalibrationObservation, evaluate_calibration
from engine.prediction import MODEL_VERSION, predict_point_football
from engine.ratings import InsufficientDataError, RatingConfig
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import as_utc
from app.models.match import Match, MatchStatus
from app.models.reference import Competition, Season, Sport
from app.schemas.calibration import CalibrationBinRead, CalibrationRead
from app.services.predictions import to_historical
from app.services.preferences import get_preferences

FOOTBALL_CODE = "football"
MAX_HISTORY = 2000
LEAGUE_WINDOW = 400
MIN_LIMIT = 10
MAX_LIMIT = 100
DEFAULT_LIMIT = 40
SMALL_SAMPLE = 30

MESSAGE_EMPTY = (
    "Aucune rencontre évaluable : l'historique est insuffisant pour un rétro-test honnête."
)
AVERTISSEMENT = (
    "Rétro-test rétrospectif : chaque rencontre est pronostiquée avec l'historique "
    "strictement antérieur à son coup d'envoi. Les rencontres sans historique "
    "suffisant sont exclues ; ce résultat ne garantit aucune performance future."
)


def _empty_report(*, now: datetime, limit: int) -> CalibrationRead:
    return CalibrationRead(
        model_version=MODEL_VERSION,
        generated_at=now,
        limit=limit,
        matches_evaluated=0,
        matches_excluded=0,
        period_start=None,
        period_end=None,
        home_wins=0,
        draws=0,
        away_wins=0,
        brier=None,
        log_loss=None,
        accuracy=None,
        baseline_brier=None,
        baseline_log_loss=None,
        brier_skill=None,
        ece=None,
        mean_xg_coverage=None,
        bins=[],
        message=MESSAGE_EMPTY,
        avertissement=AVERTISSEMENT,
    )


def build_calibration(db: Session, *, limit: int = DEFAULT_LIMIT) -> CalibrationRead:
    """Reconstruit les prévisions passées et mesure leur calibration."""
    now = datetime.now(UTC)
    sport = db.scalar(select(Sport).where(Sport.code == FOOTBALL_CODE))
    if sport is None:
        return _empty_report(now=now, limit=limit)

    rows = list(
        db.scalars(
            select(Match)
            .options(selectinload(Match.stats))
            .join(Season, Match.season_id == Season.id)
            .join(Competition, Season.competition_id == Competition.id)
            .where(
                Competition.sport_id == sport.id,
                Match.status == MatchStatus.TERMINE,
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
                Match.kickoff_at < now,
            )
            .order_by(Match.kickoff_at.desc())
            .limit(MAX_HISTORY)
        ).all()
    )
    if not rows:
        return _empty_report(now=now, limit=limit)

    rows.reverse()
    historical = [to_historical(row) for row in rows]
    preferences = get_preferences(db)
    config = RatingConfig(
        half_life_days=float(preferences.demi_vie_jours),
        max_matches_per_team=preferences.nb_matchs_historique,
    )

    start = max(0, len(rows) - limit)
    attempts = len(rows) - start
    observations: list[CalibrationObservation] = []

    for position in range(start, len(rows)):
        target = rows[position]
        pool = historical[:position]
        league = historical[max(0, position - LEAGUE_WINDOW) : position]
        try:
            prediction = predict_point_football(
                pool,
                league_matches=league,
                home_team_id=str(target.home_team_id),
                away_team_id=str(target.away_team_id),
                as_of=as_utc(target.kickoff_at),
                config=config,
            )
        except InsufficientDataError:
            continue

        markets = prediction.markets
        observations.append(
            CalibrationObservation(
                match_id=str(target.id),
                kickoff_at=as_utc(target.kickoff_at),
                home_win=markets.home_win,
                draw=markets.draw,
                away_win=markets.away_win,
                home_goals=int(target.home_score or 0),
                away_goals=int(target.away_score or 0),
                xg_coverage=min(
                    prediction.ratings.home.xg_coverage,
                    prediction.ratings.away.xg_coverage,
                ),
            )
        )

    report = evaluate_calibration(observations)
    excluded = attempts - report.matches
    if report.matches == 0:
        return CalibrationRead(
            model_version=MODEL_VERSION,
            generated_at=now,
            limit=limit,
            matches_evaluated=0,
            matches_excluded=excluded,
            period_start=None,
            period_end=None,
            home_wins=0,
            draws=0,
            away_wins=0,
            brier=None,
            log_loss=None,
            accuracy=None,
            baseline_brier=None,
            baseline_log_loss=None,
            brier_skill=None,
            ece=None,
            mean_xg_coverage=None,
            bins=[],
            message=MESSAGE_EMPTY,
            avertissement=AVERTISSEMENT,
        )

    message = f"{report.matches} rencontre(s) évaluée(s) sur les {attempts} plus récentes."
    avertissement = AVERTISSEMENT
    if report.matches < SMALL_SAMPLE:
        avertissement += (
            f" Échantillon faible ({report.matches} rencontres) : les indicateurs sont "
            "très instables."
        )

    return CalibrationRead(
        model_version=MODEL_VERSION,
        generated_at=now,
        limit=limit,
        matches_evaluated=report.matches,
        matches_excluded=excluded,
        period_start=min(item.kickoff_at for item in observations),
        period_end=max(item.kickoff_at for item in observations),
        home_wins=report.home_wins,
        draws=report.draws,
        away_wins=report.away_wins,
        brier=report.brier,
        log_loss=report.log_loss,
        accuracy=report.accuracy,
        baseline_brier=report.baseline_brier,
        baseline_log_loss=report.baseline_log_loss,
        brier_skill=report.brier_skill,
        ece=report.ece,
        mean_xg_coverage=report.mean_xg_coverage,
        bins=[
            CalibrationBinRead(
                low=item.low,
                high=item.high,
                count=item.count,
                mean_predicted=item.mean_predicted,
                observed=item.observed,
                wilson_low=item.wilson_low,
                wilson_high=item.wilson_high,
            )
            for item in report.bins
        ],
        message=message,
        avertissement=avertissement,
    )
