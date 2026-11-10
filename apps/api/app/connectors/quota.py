"""Budgets locaux et lecture des en-têtes de quota.

Les compteurs sont persistés dans `provider_usage` afin de survivre à un
redémarrage. Les en-têtes réels du fournisseur recalent le budget local : on
conserve la consommation locale et on ajuste le plafond pour que le restant
calculé corresponde au restant annoncé.
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import BudgetExceededError, QuotaInfo
from app.core.config import settings
from app.models.connector import ProviderUsage

DAY_PROVIDERS = {"bigballsdata", "football_data"}
MONTH_PROVIDERS = {"the_odds_api"}
# Fournisseurs sans quota : fichier public, aucune clé, aucun plafond.
UNLIMITED_PROVIDERS = {"football_data_uk"}


def period_kind(provider: str) -> str:
    return "month" if provider in MONTH_PROVIDERS else "day"


def period_start(provider: str, now: datetime | None = None) -> date:
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    if period_kind(provider) == "month":
        return moment.date().replace(day=1)
    return moment.date()


def budget_for(provider: str) -> int:
    if provider == "bigballsdata":
        return settings.bigballsdata_daily_budget
    if provider == "the_odds_api":
        return settings.the_odds_api_monthly_budget
    if provider == "football_data":
        return settings.football_data_minute_budget
    return 0


def get_usage(db: Session, provider: str, now: datetime | None = None) -> ProviderUsage:
    """Retourne le compteur de la période courante, créé si nécessaire."""
    start = period_start(provider, now)
    kind = period_kind(provider)
    usage = db.scalar(
        select(ProviderUsage).where(
            ProviderUsage.provider == provider,
            ProviderUsage.period_kind == kind,
            ProviderUsage.period_start == start,
        )
    )
    if usage is None:
        usage = ProviderUsage(
            provider=provider,
            period_kind=kind,
            period_start=start,
            used=0,
            limit=budget_for(provider),
        )
        db.add(usage)
        db.flush()
    return usage


def remaining(db: Session, provider: str, now: datetime | None = None) -> int:
    usage = get_usage(db, provider, now)
    return max(usage.limit - usage.used, 0)


def ensure_budget(db: Session, provider: str, amount: int, now: datetime | None = None) -> None:
    """Refuse l'appel avant consommation si le budget restant est insuffisant."""
    if amount <= 0 or provider in UNLIMITED_PROVIDERS:
        return
    available = remaining(db, provider, now)
    if amount > available:
        raise BudgetExceededError(
            f"Budget insuffisant pour {provider} : {available} unité(s) restante(s), "
            f"{amount} demandée(s). Réduisez le lot ou attendez la réinitialisation."
        )


def consume(
    db: Session, provider: str, amount: int = 1, now: datetime | None = None
) -> ProviderUsage:
    """Consomme le budget après un appel réussi ou prévu."""
    usage = get_usage(db, provider, now)
    if amount > 0:
        usage.used += amount
    db.flush()
    return usage


def apply_headers(
    db: Session,
    provider: str,
    headers: Mapping[str, str],
    now: datetime | None = None,
) -> QuotaInfo:
    """Recale le plafond local sur le restant réel annoncé par le fournisseur."""
    usage = get_usage(db, provider, now)
    lowered = {key.lower(): value for key, value in headers.items()}

    remaining_header: int | None = None
    for name in ("x-requests-remaining", "x-ratelimit-remaining", "x-rate-limit-remaining"):
        raw = lowered.get(name)
        if raw is not None:
            try:
                remaining_header = int(float(raw))
            except ValueError:
                continue
            break

    if remaining_header is not None:
        usage.limit = usage.used + max(remaining_header, 0)
        db.flush()

    return QuotaInfo(
        used=usage.used,
        remaining=max(usage.limit - usage.used, 0),
        limit=usage.limit,
        reset_at=_reset_at(provider, now),
    )


def _reset_at(provider: str, now: datetime | None) -> datetime:
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    if period_kind(provider) == "month":
        year = moment.year + (1 if moment.month == 12 else 0)
        month = 1 if moment.month == 12 else moment.month + 1
        return datetime(year, month, 1, tzinfo=UTC)
    next_day = moment.date().toordinal() + 1
    return datetime.fromordinal(next_day).replace(tzinfo=UTC)


def snapshot(db: Session, provider: str, now: datetime | None = None) -> QuotaInfo:
    if provider in UNLIMITED_PROVIDERS:
        return QuotaInfo(used=0, remaining=None, limit=None, reset_at=None)
    usage = get_usage(db, provider, now)
    return QuotaInfo(
        used=usage.used,
        remaining=max(usage.limit - usage.used, 0),
        limit=usage.limit,
        reset_at=_reset_at(provider, now),
    )
