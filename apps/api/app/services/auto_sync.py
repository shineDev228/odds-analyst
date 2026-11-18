"""Mise à jour automatique au démarrage de l'API (phase 15, étape 6).

Principe : l'application reste utilisable immédiatement. Une tâche de fond
vérifie l'âge de la dernière passe de faits **appliquée** dans `sync_runs` ;
au-delà de 24 h (ou en l'absence de passe), elle importe les faits
BigBallsData puis l'enrichissement CSV (xG et cotes de clôture).

Trois garde-fous :

1. **Jamais les cotes 1xBet** : elles dépensent des crédits et restent une
   action volontaire, depuis la page Synchronisation ou la CLI.
2. **Une seule passe à la fois** et **une nouvelle tentative par heure** au
   plus : une application laissée ouverte ne martèle pas le fournisseur.
3. **Aucun échec propagé** : une erreur réseau ou de base est journalisée,
   l'API continue de répondre. Aucune clé n'apparaît dans le journal.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.http import redact
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.connector import SyncOperation, SyncRun, SyncStatus
from app.services import csv_sync
from app.services import synchronization as facts

logger = logging.getLogger("odds_analyst.auto_sync")

# Statuts d'un rapport qui comptent comme « fait » : rien d'autre à faire.
_OK = frozenset({"applied", "empty"})


@dataclass(slots=True)
class AutoSyncOutcome:
    """Ce que la vérification a décidé et, le cas échéant, produit."""

    launched: bool = False
    status: str = "skipped"
    reason: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    facts_status: str | None = None
    csv_status: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "launched": self.launched,
            "status": self.status,
            "reason": self.reason,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "facts_status": self.facts_status,
            "csv_status": self.csv_status,
            "details": self.details,
        }


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite renvoie des dates naïves : on les traite comme UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def last_run(db: Session, *, status: str | None = None) -> SyncRun | None:
    """Dernière passe de faits journalisée, éventuellement filtrée par statut."""
    query = select(SyncRun).where(SyncRun.operation == SyncOperation.FIXTURES.value)
    if status is not None:
        query = query.where(SyncRun.status == status)
    return db.scalars(query.order_by(SyncRun.created_at.desc()).limit(1)).first()


def last_applied_at(db: Session) -> datetime | None:
    """Date de la dernière passe de faits appliquée, en UTC."""
    run = last_run(db, status=SyncStatus.APPLIED.value)
    return _as_utc(run.created_at) if run is not None else None


def is_due(
    db: Session,
    now: datetime | None = None,
    *,
    interval_hours: float | None = None,
    retry_minutes: int = 60,
) -> bool:
    """Une passe est-elle nécessaire ?

    Deux règles, dans cet ordre :

    1. une passe appliquée de moins de ``interval_hours`` ferme la porte ;
    2. sinon, une tentative de faits de moins de ``retry_minutes`` aussi,
       pour ne pas répéter un échec à chaque vérification.
    """
    if not settings.auto_sync_enabled:
        return False
    moment = _as_utc(now) or datetime.now(UTC)
    interval = (
        settings.auto_sync_interval_hours if interval_hours is None else interval_hours
    )
    applied = last_run(db, status=SyncStatus.APPLIED.value)
    if applied is not None:
        applied_at = _as_utc(applied.created_at)
        if applied_at is not None and moment - applied_at < timedelta(hours=interval):
            return False
    recent = last_run(db)
    if recent is not None:
        recent_at = _as_utc(recent.created_at)
        if recent_at is not None and moment - recent_at < timedelta(minutes=retry_minutes):
            return False
    return True


def _rollup(facts_status: str | None, csv_status: str | None) -> str:
    """Statut d'ensemble : appliqué seulement si tout est appliqué."""
    statuses = [value for value in (facts_status, csv_status) if value]
    if not statuses:
        return "skipped"
    if all(value in _OK for value in statuses):
        return "applied"
    if all(value == "failed" for value in statuses):
        return "failed"
    return "partial"


def _run(
    outcome: AutoSyncOutcome,
    moment: datetime,
    *,
    session_factory: Callable[[], Session],
    leagues: list[str] | None,
    stats_limit: int | None,
    sleep: Callable[[float], None],
) -> None:
    if not settings.bigballsdata_key:
        outcome.reason = (
            "Clé BigBallsData absente : aucune mise à jour automatique lancée."
        )
        return

    db = session_factory()
    try:
        if not is_due(db, moment):
            outcome.reason = "Dernière synchronisation des faits récente : rien à faire."
            return

        outcome.launched = True
        report = facts.run_sync(
            db,
            leagues=leagues,
            include_stats=True,
            include_standings=True,
            stats_limit=(
                settings.auto_sync_stats_limit if stats_limit is None else stats_limit
            ),
            now=moment,
            sleep=sleep,
        )
        outcome.facts_status = report.status

        if report.status in {"applied", "partial"}:
            download = csv_sync.download(db, now=moment)
            imported = csv_sync.run(db, refresh=False, now=moment)
            outcome.csv_status = imported.status
            outcome.details = {
                "csv_files": download.as_dict().get("totals", {}),
                "csv_import": imported.as_dict().get("totals", {}),
            }
        elif report.error:
            outcome.details = {"facts_error": report.error}

        db.commit()
        outcome.status = _rollup(outcome.facts_status, outcome.csv_status)
        outcome.reason = (
            f"Faits : {outcome.facts_status} · CSV : "
            f"{outcome.csv_status or 'non lancé'}."
        )
    except Exception as exc:
        db.rollback()
        outcome.status = "failed"
        outcome.reason = "Mise à jour automatique interrompue par une erreur inattendue."
        logger.warning(
            "Mise à jour automatique en échec (%s) : %s",
            exc.__class__.__name__,
            redact(str(exc)),
        )
    finally:
        db.close()


def run_once(
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    now: datetime | None = None,
    leagues: list[str] | None = None,
    stats_limit: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> AutoSyncOutcome:
    """Vérifie puis, si nécessaire, importe faits et CSV dans une transaction."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    outcome = AutoSyncOutcome(started_at=moment)
    if not settings.auto_sync_enabled:
        outcome.reason = "Mise à jour automatique désactivée."
        outcome.finished_at = moment
        return outcome
    try:
        _run(
            outcome,
            moment,
            session_factory=session_factory,
            leagues=leagues,
            stats_limit=stats_limit,
            sleep=sleep,
        )
    finally:
        outcome.finished_at = datetime.now(UTC)
    return outcome


class AutoSyncScheduler:
    """Boucle de fond : une vérification après le démarrage, puis à intervalle fixe.

    Un seul processus API est supposé : le verrou en mémoire évite deux passes
    dans la même instance, ``is_due`` protège des doublons entre deux
    démarrages rapprochés (par exemple ``uvicorn --reload``).
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        startup_delay_seconds: float | None = None,
        check_minutes: float | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._startup_delay = (
            settings.auto_sync_startup_delay_seconds
            if startup_delay_seconds is None
            else startup_delay_seconds
        )
        self._check_minutes = (
            settings.auto_sync_check_minutes
            if check_minutes is None
            else check_minutes
        )
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self.last_outcome: AutoSyncOutcome | None = None

    def start(self) -> bool:
        """Programme la boucle ; renvoie False si elle n'a pas été lancée."""
        if not settings.auto_sync_enabled:
            logger.info(
                "Mise à jour automatique désactivée (AUTO_SYNC_ENABLED=false)."
            )
            return False
        if self._task is not None and not self._task.done():
            return False
        try:
            self._task = asyncio.create_task(self._loop(), name="auto-sync")
        except RuntimeError:
            logger.warning(
                "Mise à jour automatique non programmée : aucune boucle asyncio."
            )
            return False
        logger.info(
            "Mise à jour automatique programmée : première vérification dans %s s, "
            "puis toutes les %s min.",
            int(max(self._startup_delay, 0)),
            int(max(self._check_minutes, 1)),
        )
        return True

    async def stop(self) -> None:
        """Annule la boucle et attend son arrêt complet."""
        task, self._task = self._task, None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning(
                "Arrêt de la mise à jour automatique en erreur (%s) : %s",
                exc.__class__.__name__,
                redact(str(exc)),
            )

    async def check(self, *, now: datetime | None = None) -> AutoSyncOutcome | None:
        """Exécute une vérification hors de la boucle d'événements."""
        if not settings.auto_sync_enabled:
            return None
        if self._lock.locked():
            logger.info("Mise à jour automatique déjà en cours : vérification ignorée.")
            return None
        async with self._lock:
            try:
                outcome = await asyncio.to_thread(
                    run_once,
                    session_factory=self._session_factory,
                    now=now,
                )
            except Exception as exc:
                logger.warning(
                    "Mise à jour automatique : échec inattendu (%s) : %s",
                    exc.__class__.__name__,
                    redact(str(exc)),
                )
                return None
            self.last_outcome = outcome
            if outcome.launched:
                logger.info(
                    "Mise à jour automatique : faits=%s, csv=%s, statut=%s.",
                    outcome.facts_status or "non lancé",
                    outcome.csv_status or "non lancé",
                    outcome.status,
                )
            else:
                logger.info("Mise à jour automatique : %s", outcome.reason)
            return outcome

    async def _loop(self) -> None:
        try:
            if self._startup_delay > 0:
                await asyncio.sleep(self._startup_delay)
            while True:
                await self.check()
                await asyncio.sleep(max(self._check_minutes, 1) * 60)
        except asyncio.CancelledError:
            raise
