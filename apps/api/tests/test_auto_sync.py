"""Tests du déclencheur automatique : décision, exécution, boucle de fond.

Aucun appel réseau : les services sont remplacés par des doublures. Le
déclencheur est désactivé globalement dans ``conftest.py`` ; chaque test
l'active explicitement.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from app.core.config import settings
from app.models.connector import SyncRun
from app.services import auto_sync


@pytest.fixture()
def enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auto_sync_enabled", True)


@pytest.fixture()
def configured(monkeypatch: pytest.MonkeyPatch, enabled: None) -> None:
    monkeypatch.setattr(settings, "bigballsdata_key", "cle-de-test")


def _record(
    session_factory: Any,
    *,
    operation: str = "fixtures",
    status: str = "applied",
    age: timedelta | None = None,
    provider: str = "bigballsdata",
) -> None:
    with session_factory() as db:
        run = SyncRun(
            provider=provider,
            operation=operation,
            status=status,
            params={},
            summary={},
        )
        if age is not None:
            run.created_at = datetime.now(UTC) - age
        db.add(run)
        db.commit()


def _report(status: str, error: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        error=error,
        as_dict=lambda: {"status": status, "totals": {}},
    )


# --- Décision --------------------------------------------------------------


def test_due_without_history(enabled: None, session_factory) -> None:
    with session_factory() as db:
        assert auto_sync.is_due(db) is True
        assert auto_sync.last_applied_at(db) is None


def test_not_due_when_recently_applied(enabled: None, session_factory) -> None:
    _record(session_factory, age=timedelta(hours=23))
    with session_factory() as db:
        assert auto_sync.is_due(db) is False


def test_due_after_interval(enabled: None, session_factory) -> None:
    _record(session_factory, age=timedelta(hours=25))
    with session_factory() as db:
        assert auto_sync.is_due(db) is True
        assert auto_sync.last_applied_at(db) is not None


def test_not_due_after_recent_failure(enabled: None, session_factory) -> None:
    _record(session_factory, status="failed", age=timedelta(minutes=10))
    with session_factory() as db:
        assert auto_sync.is_due(db) is False


def test_due_after_retry_window(enabled: None, session_factory) -> None:
    _record(session_factory, status="failed", age=timedelta(hours=2))
    with session_factory() as db:
        assert auto_sync.is_due(db) is True


def test_csv_runs_do_not_reset_facts_clock(enabled: None, session_factory) -> None:
    _record(
        session_factory,
        operation="csv",
        status="applied",
        age=timedelta(minutes=5),
        provider="football_data_uk",
    )
    with session_factory() as db:
        assert auto_sync.is_due(db) is True


def test_disabled_is_never_due(session_factory) -> None:
    _record(session_factory, age=timedelta(days=30))
    with session_factory() as db:
        assert auto_sync.is_due(db) is False


# --- Exécution -------------------------------------------------------------


def test_run_once_imports_facts_then_csv(
    configured: None, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_facts(db, **kwargs):
        calls.append("facts")
        assert kwargs["include_stats"] is True
        assert kwargs["include_standings"] is True
        assert kwargs["stats_limit"] == settings.auto_sync_stats_limit
        return _report("applied")

    def fake_download(db, **kwargs):
        calls.append("download")
        return _report("applied")

    def fake_import(db, **kwargs):
        calls.append("import")
        assert kwargs["refresh"] is False
        return _report("applied")

    monkeypatch.setattr(auto_sync.facts, "run_sync", fake_facts)
    monkeypatch.setattr(auto_sync.csv_sync, "download", fake_download)
    monkeypatch.setattr(auto_sync.csv_sync, "run", fake_import)

    outcome = auto_sync.run_once(session_factory=session_factory)

    assert outcome.launched is True
    assert outcome.status == "applied"
    assert outcome.facts_status == "applied"
    assert outcome.csv_status == "applied"
    assert calls == ["facts", "download", "import"]


def test_run_once_never_imports_odds(
    configured: None, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interdit(*args, **kwargs):
        raise AssertionError("les cotes ne doivent jamais être importées en automatique")

    monkeypatch.setattr(auto_sync.facts, "run_sync", lambda db, **kw: _report("applied"))
    monkeypatch.setattr(auto_sync.csv_sync, "download", lambda db, **kw: _report("applied"))
    monkeypatch.setattr(auto_sync.csv_sync, "run", lambda db, **kw: _report("applied"))
    monkeypatch.setattr("app.services.odds_sync.run", interdit)
    monkeypatch.setattr("app.services.odds_sync.preview", interdit)

    outcome = auto_sync.run_once(session_factory=session_factory)

    assert outcome.status == "applied"


def test_run_once_skips_without_key(
    enabled: None, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "bigballsdata_key", "")

    def interdit(*args, **kwargs):
        raise AssertionError("aucun appel ne doit partir sans clé")

    monkeypatch.setattr(auto_sync.facts, "run_sync", interdit)

    outcome = auto_sync.run_once(session_factory=session_factory)

    assert outcome.launched is False
    assert "Clé BigBallsData absente" in outcome.reason


def test_run_once_skips_when_recent(
    configured: None, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record(session_factory, age=timedelta(hours=2))

    def interdit(*args, **kwargs):
        raise AssertionError("une passe récente ne doit pas être rejouée")

    monkeypatch.setattr(auto_sync.facts, "run_sync", interdit)

    outcome = auto_sync.run_once(session_factory=session_factory)

    assert outcome.launched is False
    assert "récente" in outcome.reason


def test_run_once_skips_csv_when_facts_fail(
    configured: None, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auto_sync.facts, "run_sync", lambda db, **kw: _report("failed"))

    def interdit(*args, **kwargs):
        raise AssertionError("sans faits, le CSV n'a rien à enrichir")

    monkeypatch.setattr(auto_sync.csv_sync, "download", interdit)
    monkeypatch.setattr(auto_sync.csv_sync, "run", interdit)

    outcome = auto_sync.run_once(session_factory=session_factory)

    assert outcome.launched is True
    assert outcome.status == "failed"
    assert outcome.csv_status is None


def test_run_once_swallows_unexpected_error(
    configured: None, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("réseau indisponible")

    monkeypatch.setattr(auto_sync.facts, "run_sync", boom)

    outcome = auto_sync.run_once(session_factory=session_factory)

    assert outcome.launched is True
    assert outcome.status == "failed"
    assert "erreur inattendue" in outcome.reason


def test_run_once_partial_rolls_up(
    configured: None, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auto_sync.facts, "run_sync", lambda db, **kw: _report("partial"))
    monkeypatch.setattr(auto_sync.csv_sync, "download", lambda db, **kw: _report("applied"))
    monkeypatch.setattr(auto_sync.csv_sync, "run", lambda db, **kw: _report("failed"))

    outcome = auto_sync.run_once(session_factory=session_factory)

    assert outcome.status == "partial"


# --- Boucle de fond --------------------------------------------------------


def test_scheduler_stays_stopped_when_disabled() -> None:
    scheduler = auto_sync.AutoSyncScheduler()
    assert scheduler.start() is False
    assert scheduler._task is None


def test_scheduler_start_and_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auto_sync_enabled", True)
    monkeypatch.setattr(settings, "auto_sync_startup_delay_seconds", 3600)
    monkeypatch.setattr(settings, "auto_sync_check_minutes", 60)

    async def scenario() -> None:
        scheduler = auto_sync.AutoSyncScheduler()
        assert scheduler.start() is True
        assert scheduler.start() is False  # jamais deux boucles
        await scheduler.stop()
        assert scheduler._task is None

    asyncio.run(scenario())


def test_scheduler_check_runs_once(
    enabled: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome = auto_sync.AutoSyncOutcome(launched=False, reason="rien à faire")
    calls: list[Any] = []

    def fake_run_once(**kwargs):
        calls.append(kwargs)
        return outcome

    monkeypatch.setattr(auto_sync, "run_once", fake_run_once)
    scheduler = auto_sync.AutoSyncScheduler()

    result = asyncio.run(scheduler.check())

    assert result is outcome
    assert scheduler.last_outcome is outcome
    assert len(calls) == 1


def test_scheduler_check_disabled_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def interdit(**kwargs):
        raise AssertionError("désactivé : aucun lancement")

    monkeypatch.setattr(auto_sync, "run_once", interdit)
    scheduler = auto_sync.AutoSyncScheduler()

    assert asyncio.run(scheduler.check()) is None


# --- Branchement dans l'application ---------------------------------------


def test_lifespan_exposes_scheduler(client) -> None:
    scheduler = client.app.state.auto_sync
    assert isinstance(scheduler, auto_sync.AutoSyncScheduler)
    # Le déclencheur est coupé par la fixture autouse : aucune tâche en vol.
    assert scheduler._task is None
