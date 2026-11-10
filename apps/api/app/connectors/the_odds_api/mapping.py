"""Mapping pur des cotes The Odds API vers les marchés internes.

Seuls `h2h`, `totals`, `double_chance` et `btts` sont reconnus. Toute autre
clé est ignorée. Aucune cote n'est dérivée d'un autre marché.
"""

from datetime import UTC, datetime
from typing import Any

from app.connectors.base import NormalizedEventOdds, NormalizedMarket
from app.connectors.matching import normalize_name

BOOKMAKER_KEY = "onexbet"
BOOKMAKER_LABEL = "1xBet"
MIN_PRICE = 1.01
MAX_PRICE = 1000.0

_DRAW_NAMES = {"draw", "tie", "nul", "x"}
_YES_NAMES = {"yes", "oui"}
_NO_NAMES = {"no", "non"}


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        raise ValueError("Date absente")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def valid_price(value: Any) -> float | None:
    """Prix décimal accepté, hors bornes rejeté."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    price = float(value)
    if price <= MIN_PRICE or price >= MAX_PRICE:
        return None
    return round(price, 6)


def _side_code(name: str, home: str, away: str) -> str | None:
    normalized = normalize_name(name)
    if normalized == normalize_name(home):
        return "1"
    if normalized in _DRAW_NAMES:
        return "X"
    if normalized == normalize_name(away):
        return "2"
    return None


def _double_chance_code(name: str, home: str, away: str) -> str | None:
    literal = name.strip().upper().replace(" ", "")
    if literal in {"1X", "12", "X2"}:
        return literal

    normalized = normalize_name(name)
    segments = [
        segment.strip()
        for segment in normalized.replace("/", " or ").split(" or ")
        if segment.strip()
    ]
    flags = set()
    for segment in segments:
        if segment == normalize_name(home):
            flags.add("home")
        elif segment == normalize_name(away):
            flags.add("away")
        elif segment in _DRAW_NAMES:
            flags.add("draw")
    if flags == {"home", "draw"}:
        return "1X"
    if flags == {"home", "away"}:
        return "12"
    if flags == {"draw", "away"}:
        return "X2"
    return None


def _btts_code(name: str) -> str | None:
    normalized = normalize_name(name)
    if normalized in _YES_NAMES:
        return "oui"
    if normalized in _NO_NAMES:
        return "non"
    return None


def _h2h(outcomes: list[Any], home: str, away: str) -> tuple[dict[str, float], bool]:
    prices: dict[str, float] = {}
    complete = True
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            complete = False
            continue
        code = _side_code(str(outcome.get("name") or ""), home, away)
        price = valid_price(outcome.get("price"))
        if code is None or price is None or code in prices:
            complete = False
            continue
        prices[code] = price
    return prices, complete and {"1", "X", "2"} <= prices.keys()


def _totals(outcomes: list[Any]) -> tuple[list[NormalizedMarket], int]:
    grouped: dict[float, dict[str, float]] = {}
    ignored = 0
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            ignored += 1
            continue
        point = outcome.get("point")
        name = normalize_name(str(outcome.get("name") or ""))
        price = valid_price(outcome.get("price"))
        if not isinstance(point, (int, float)) or price is None:
            ignored += 1
            continue
        if name in {"over", "plus"}:
            code = "plus"
        elif name in {"under", "moins"}:
            code = "moins"
        else:
            code = None
        if code is None:
            ignored += 1
            continue
        grouped.setdefault(float(point), {})[code] = price

    markets: list[NormalizedMarket] = []
    for line, prices in sorted(grouped.items()):
        if {"plus", "moins"} <= prices.keys():
            markets.append(
                NormalizedMarket(
                    template_code="football.total_buts",
                    line=line,
                    outcomes=prices,
                )
            )
        else:
            ignored += 1
    return markets, ignored


def _double_chance(outcomes: list[Any], home: str, away: str) -> tuple[dict[str, float], bool]:
    prices: dict[str, float] = {}
    complete = True
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            complete = False
            continue
        code = _double_chance_code(str(outcome.get("name") or ""), home, away)
        price = valid_price(outcome.get("price"))
        if code is None or price is None or code in prices:
            complete = False
            continue
        prices[code] = price
    return prices, complete and {"1X", "12", "X2"} <= prices.keys()


def _btts(outcomes: list[Any]) -> tuple[dict[str, float], bool]:
    prices: dict[str, float] = {}
    complete = True
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            complete = False
            continue
        code = _btts_code(str(outcome.get("name") or ""))
        price = valid_price(outcome.get("price"))
        if code is None or price is None or code in prices:
            complete = False
            continue
        prices[code] = price
    return prices, complete and {"oui", "non"} <= prices.keys()


def map_event_odds(
    raw: dict[str, Any], *, bookmaker_key: str = BOOKMAKER_KEY, allowed: set[str] | None = None
) -> NormalizedEventOdds | None:
    """Extrait les cotes 1xBet d'un événement.

    Renvoie `None` si le bookmaker est absent. Les marchés incomplets sont
    ignorés et comptés, jamais complétés.
    """
    bookmakers = raw.get("bookmakers")
    if not isinstance(bookmakers, list):
        return None
    bookmaker = next(
        (
            item
            for item in bookmakers
            if isinstance(item, dict) and item.get("key") == bookmaker_key
        ),
        None,
    )
    if bookmaker is None:
        return None

    home = str(raw.get("home_team") or "")
    away = str(raw.get("away_team") or "")
    event_id = str(raw.get("id") or "")
    if not event_id or not home or not away:
        return None

    try:
        commence_time = parse_datetime(raw.get("commence_time"))
    except ValueError:
        return None
    try:
        captured_at = parse_datetime(bookmaker.get("last_update"))
    except ValueError:
        captured_at = datetime.now(UTC)

    markets: list[NormalizedMarket] = []
    ignored = 0
    for market in bookmaker.get("markets") or []:
        if not isinstance(market, dict):
            ignored += 1
            continue
        key = str(market.get("key") or "")
        if allowed is not None and key not in allowed:
            continue
        outcomes = market.get("outcomes")
        if not isinstance(outcomes, list):
            ignored += 1
            continue
        if key == "h2h":
            prices, complete = _h2h(outcomes, home, away)
            if complete:
                markets.append(
                    NormalizedMarket(template_code="football.resultat_1x2", outcomes=prices)
                )
            else:
                ignored += 1
        elif key == "totals":
            total_markets, skipped = _totals(outcomes)
            markets.extend(total_markets)
            ignored += skipped
        elif key == "double_chance":
            prices, complete = _double_chance(outcomes, home, away)
            if complete:
                markets.append(
                    NormalizedMarket(template_code="football.double_chance", outcomes=prices)
                )
            else:
                ignored += 1
        elif key == "btts":
            prices, complete = _btts(outcomes)
            if complete:
                markets.append(NormalizedMarket(template_code="football.btts", outcomes=prices))
            else:
                ignored += 1

    return NormalizedEventOdds(
        event_id=event_id,
        home_team=home,
        away_team=away,
        commence_time=commence_time,
        bookmaker=BOOKMAKER_LABEL,
        captured_at=captured_at,
        markets=markets,
        ignored=ignored,
    )


def map_events(
    raw_events: list[Any], *, allowed: set[str] | None = None
) -> list[NormalizedEventOdds]:
    """Mappe une liste d'événements en ignorant proprement les entrées invalides."""
    result: list[NormalizedEventOdds] = []
    for raw in raw_events:
        if not isinstance(raw, dict):
            continue
        mapped = map_event_odds(raw, allowed=allowed)
        if mapped is not None:
            result.append(mapped)
    return result
