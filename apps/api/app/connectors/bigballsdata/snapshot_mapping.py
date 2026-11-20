"""Normalisation d'une équipe BigBallsData en une ligne de snapshot.

Aucune valeur n'est recalculée : l'Elo et les fréquences viennent du
fournisseur. Une donnée absente, illisible ou hors bornes devient ``None`` et
produit un avertissement ; aucune exception n'est levée pour une valeur
aberrante, car une ligne partielle vaut mieux qu'une passe interrompue.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from app.connectors.bigballsdata.mapping import parse_datetime

FORM_LENGTH = 10
# Bornes defendables pour une note Elo et une cote stockée en base.
ELO_MAX = Decimal("99999.99")
# Numeric(7,3) accepte au plus 9999,999.
PRICE_MAX = Decimal("9999.999")
# /v1/games mélange deux écritures : américaine (+114, -112) et décimale (2,25).
AMERICAN_MIN = Decimal(100)
PRICE_ROUND = Decimal("0.001")
SLOTS = ("morning", "evening")


@dataclass(slots=True)
class NormalizedTeamSnapshot:
    """Valeurs d'une équipe pour un jour, prêtes à être écrites."""

    team_external_id: str
    captured_on: date
    captured_at: datetime
    source_as_of: datetime | None = None

    elo_rating: Decimal | None = None
    elo_games_counted: int | None = None
    elo_last_match_date: date | None = None

    matches_played: int | None = None
    btts_rate: Decimal | None = None
    over_2_5_rate: Decimal | None = None
    goals_scored: int | None = None
    goals_conceded: int | None = None
    clean_sheets: int | None = None
    form_string: str | None = None

    home_wins: int | None = None
    home_draws: int | None = None
    home_losses: int | None = None
    away_wins: int | None = None
    away_draws: int | None = None
    away_losses: int | None = None

    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NormalizedMarketBoard:
    """Cotes agrégées d'une rencontre, pour un créneau donné."""

    external_match_id: str
    captured_on: date
    snapshot_slot: str
    captured_at: datetime
    scheduled_at: datetime | None = None
    status: str | None = None
    odds_updated_at: datetime | None = None
    books_count: int | None = None
    home_decimal: Decimal | None = None
    away_decimal: Decimal | None = None
    total_line: Decimal | None = None
    over_decimal: Decimal | None = None
    under_decimal: Decimal | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def has_values(self) -> bool:
        """Une ligne sans aucune des quatre cotes n'apporte rien."""
        return any(
            value is not None
            for value in (
                self.home_decimal,
                self.away_decimal,
                self.over_decimal,
                self.under_decimal,
            )
        )


def map_team_snapshot(
    *,
    team_external_id: str,
    elo: Any,
    stats: Any,
    season: Any,
    captured_at: datetime,
    timezone: str,
) -> NormalizedTeamSnapshot:
    """Combine les trois réponses du fournisseur en une seule ligne.

    ``elo``, ``stats`` et ``season`` peuvent être vides : la ligne est créée
    avec les seules valeurs disponibles. ``source_as_of`` est le plus ancien
    des trois horodatages, pour ne jamais paraître plus frais que sa
    composante la plus ancienne.
    """
    warnings: list[str] = []
    elo_data = _dict(elo)
    stats_data = _dict(stats)
    season_data = _dict(season)

    moment = captured_at if captured_at.tzinfo is not None else captured_at.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)
    captured_on = _local_day(moment, timezone, warnings)

    elo_rating = _elo_rating(elo_data.get("elo_rating"), warnings)
    last_match_date = _date(elo_data.get("last_match_date"), "elo.last_match_date", warnings)
    last_computed = _instant(elo_data.get("last_computed"), "elo.last_computed", warnings)
    stats_as_of = _instant(stats_data.get("as_of"), "stats.as_of", warnings)
    season_as_of = _instant(season_data.get("as_of"), "season.as_of", warnings)

    home = _split(season_data, "home", warnings)
    away = _split(season_data, "away", warnings)

    return NormalizedTeamSnapshot(
        team_external_id=team_external_id,
        captured_on=captured_on,
        captured_at=moment,
        source_as_of=_oldest(last_computed, stats_as_of, season_as_of),
        elo_rating=elo_rating,
        elo_games_counted=_count(elo_data.get("games_counted"), "elo.games_counted", warnings),
        elo_last_match_date=last_match_date,
        matches_played=_count(stats_data.get("matches_played"), "stats.matches_played", warnings),
        btts_rate=_rate(stats_data.get("btts_rate"), "stats.btts_rate", warnings),
        over_2_5_rate=_rate(stats_data.get("over_2_5_rate"), "stats.over_2_5_rate", warnings),
        goals_scored=_count(stats_data.get("goals_scored"), "stats.goals_scored", warnings),
        goals_conceded=_count(
            stats_data.get("goals_conceded"), "stats.goals_conceded", warnings
        ),
        clean_sheets=_count(stats_data.get("clean_sheets"), "stats.clean_sheets", warnings),
        form_string=_form(stats_data.get("form_string"), warnings),
        home_wins=home[0],
        home_draws=home[1],
        home_losses=home[2],
        away_wins=away[0],
        away_draws=away[1],
        away_losses=away[2],
        warnings=warnings,
    )


def map_market_board_snapshot(
    *,
    game: Any,
    slot: str,
    captured_at: datetime,
    timezone: str,
) -> NormalizedMarketBoard:
    """Normalise une rencontre de ``/v1/games``, sans extrapoler aucun côté.

    L'appelant a déjà écarté les rencontres sans cotes, commencées ou non
    appariées. Une cote manquante reste ``None`` ; une cote invalide devient
    ``None`` avec un avertissement.
    """
    if not isinstance(game, dict) or not game.get("game_id"):
        raise ValueError("Rencontre sans identifiant")
    if slot not in SLOTS:
        raise ValueError(f"Créneau inconnu : {slot}")

    warnings: list[str] = []
    moment = captured_at if captured_at.tzinfo is not None else captured_at.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)
    odds = _dict(game.get("odds"))
    moneyline = _dict(odds.get("moneyline"))
    total = _dict(odds.get("total"))

    return NormalizedMarketBoard(
        external_match_id=str(game["game_id"]),
        captured_on=_local_day(moment, timezone, warnings),
        snapshot_slot=slot,
        captured_at=moment,
        scheduled_at=_instant(game.get("scheduled_at"), "scheduled_at", warnings),
        status=_text(game.get("status")),
        odds_updated_at=_instant(
            odds.get("odds_updated_at"), "odds.odds_updated_at", warnings
        ),
        books_count=_count(odds.get("books_count"), "odds.books_count", warnings),
        home_decimal=_price(moneyline.get("home"), "odds.moneyline.home", warnings),
        away_decimal=_price(moneyline.get("away"), "odds.moneyline.away", warnings),
        total_line=_line(total.get("line"), warnings),
        over_decimal=_price(total.get("over_juice"), "odds.total.over_juice", warnings),
        under_decimal=_price(total.get("under_juice"), "odds.total.under_juice", warnings),
        warnings=warnings,
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _local_day(moment: datetime, timezone: str, warnings: list[str]) -> date:
    try:
        zone = ZoneInfo(timezone)
    except (KeyError, ValueError):
        warnings.append(f"Fuseau « {timezone} » inconnu : Europe/Paris utilisé.")
        zone = ZoneInfo("Europe/Paris")
    return moment.astimezone(zone).date()


def _oldest(*values: datetime | None) -> datetime | None:
    known = [value for value in values if value is not None]
    return min(known) if known else None


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _elo_rating(value: Any, warnings: list[str]) -> Decimal | None:
    if value is None:
        return None
    number = _number(value)
    if number is None:
        warnings.append("elo.elo_rating illisible : valeur ignorée.")
        return None
    if number < 0 or number > ELO_MAX:
        warnings.append("elo.elo_rating hors bornes : valeur ignorée.")
        return None
    return number


def _count(value: Any, label: str, warnings: list[str]) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        warnings.append(f"{label} illisible : valeur ignorée.")
        return None
    number = int(value)
    if number < 0:
        warnings.append(f"{label} négatif : valeur ignorée.")
        return None
    return number


def _rate(value: Any, label: str, warnings: list[str]) -> Decimal | None:
    if value is None:
        return None
    number = _number(value)
    if number is None:
        warnings.append(f"{label} illisible : valeur ignorée.")
        return None
    if number < 0 or number > 1:
        warnings.append(f"{label} hors bornes [0 ; 1] : valeur ignorée.")
        return None
    return number


def _form(value: Any, warnings: list[str]) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > FORM_LENGTH:
        warnings.append(f"stats.form_string tronqué à {FORM_LENGTH} caractères.")
        return text[:FORM_LENGTH]
    return text


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _price(value: Any, label: str, warnings: list[str]) -> Decimal | None:
    """Ramène une cote à une décimale, sans extrapoler.

    Le fournisseur mélange deux écritures : américaine (``+114``, ``-112``) et
    décimale (``2,25``). Une cote américaine de magnitude au moins 100 est
    convertie (``+114`` → ``2,140``, ``-112`` → ``1,893``) ; une valeur
    strictement comprise entre 1 et 100 est déjà décimale et conservée telle
    quelle. Toute autre valeur est rejetée avec un avertissement plutôt que
    stockée dans une unité douteuse.
    """
    if value is None:
        return None
    number = _number(value)
    if number is None:
        warnings.append(f"{label} illisible : valeur ignorée.")
        return None
    if number >= AMERICAN_MIN:
        decimal = Decimal(1) + number / Decimal(100)
    elif number <= -AMERICAN_MIN:
        decimal = Decimal(1) + Decimal(100) / -number
    elif number > 1:
        decimal = number
    else:
        warnings.append(f"{label} hors format (≤ 1) : valeur ignorée.")
        return None
    # numeric(7,3) : arrondi au millième pour que le rejeu soit idempotent.
    decimal = decimal.quantize(PRICE_ROUND, rounding=ROUND_HALF_UP)
    if decimal <= 1 or decimal > PRICE_MAX:
        warnings.append(f"{label} hors bornes après conversion : valeur ignorée.")
        return None
    return decimal


def _line(value: Any, warnings: list[str]) -> Decimal | None:
    if value is None:
        return None
    number = _number(value)
    if number is None:
        warnings.append("odds.total.line illisible : valeur ignorée.")
        return None
    if number < 0:
        warnings.append("odds.total.line négatif : valeur ignorée.")
        return None
    return number


def _date(value: Any, label: str, warnings: list[str]) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            pass
    warnings.append(f"{label} illisible : valeur ignorée.")
    return None


def _instant(value: Any, label: str, warnings: list[str]) -> datetime | None:
    if value is None:
        return None
    try:
        return parse_datetime(value)
    except (TypeError, ValueError):
        warnings.append(f"{label} illisible : horodatage ignoré.")
        return None


def _split(season: dict[str, Any], side: str, warnings: list[str]) -> tuple[int | None, ...]:
    splits = _dict(season.get("home_away_splits"))
    block = _dict(splits.get(side))
    if not block:
        return (None, None, None)
    return (
        _count(block.get("wins"), f"season.{side}.wins", warnings),
        # Le fournisseur nomme « ties » ce que la base appelle « draws ».
        _count(block.get("ties"), f"season.{side}.ties", warnings),
        _count(block.get("losses"), f"season.{side}.losses", warnings),
    )


__all__ = [
    "NormalizedMarketBoard",
    "NormalizedTeamSnapshot",
    "map_market_board_snapshot",
    "map_team_snapshot",
]
