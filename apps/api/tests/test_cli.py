"""Tests de la ligne de commande : commandes, options, codes de sortie, JSON.

Aucun réseau : les services sont remplacés par des doublures et la session
pointe sur la base SQLite des tests.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from app import cli
from app.core.config import settings
from app.services import csv_sync, odds_sync
from app.services import synchronization as facts


@pytest.fixture()
def cli_db(monkeypatch: pytest.MonkeyPatch, session_factory) -> None:
    monkeypatch.setattr(cli, "SessionLocal", session_factory)


def _facts_report(status: str, error: str | None = None) -> facts.SyncReport:
    return facts.SyncReport(status=status, error=error)


def _odds_report(status: str, credits: int = 0) -> odds_sync.OddsReport:
    return odds_sync.OddsReport(status=status, credits_used=credits)


@pytest.mark.parametrize(
    ("status", "expected"),
    [("applied", 0), ("empty", 0), ("partial", 3), ("failed", 1)],
)
def test_facts_exit_codes(
    cli_db: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: str,
    expected: int,
) -> None:
    monkeypatch.setattr(cli.facts, "run_sync", lambda db, **kw: _facts_report(status))

    assert cli.main(["facts"]) == expected

    sortie = capsys.readouterr().out
    assert "Synchronisation BigBallsData" in sortie
    assert cli._label(status) in sortie


def test_facts_forwards_options(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake(db, **kwargs):
        captured.update(kwargs)
        return _facts_report("applied")

    monkeypatch.setattr(cli.facts, "run_sync", fake)

    assert (
        cli.main(
            ["facts", "--leagues", "ligue1, epl", "--stats", "--standings", "--stats-limit", "5"]
        )
        == 0
    )
    assert captured["leagues"] == ["ligue1", "epl"]
    assert captured["include_stats"] is True
    assert captured["include_standings"] is True
    assert captured["stats_limit"] == 5


def test_facts_default_options(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake(db, **kwargs):
        captured.update(kwargs)
        return _facts_report("applied")

    monkeypatch.setattr(cli.facts, "run_sync", fake)

    assert cli.main(["facts"]) == 0
    assert captured["leagues"] is None
    assert captured["include_stats"] is False
    assert captured["include_standings"] is False
    assert captured["stats_limit"] == 20


def test_unknown_league_is_a_usage_error(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interdit(db, **kwargs):
        raise AssertionError("aucun service ne doit être appelé")

    monkeypatch.setattr(cli.facts, "run_sync", interdit)

    with pytest.raises(SystemExit) as error:
        cli.main(["facts", "--leagues", "ligue1, inconnue"])
    assert error.value.code == 2


def test_stats_limit_out_of_range_is_a_usage_error(cli_db: None) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["facts", "--stats-limit", "999"])
    assert error.value.code == 2


def test_missing_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as error:
        cli.main([])
    assert error.value.code == 2


def test_csv_download_never_imports(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli.csv_sync, "download", lambda db, **kw: csv_sync.CsvDownloadReport()
    )

    def interdit(*args, **kwargs):
        raise AssertionError("csv-download ne doit pas importer")

    monkeypatch.setattr(cli.csv_sync, "run", interdit)

    assert cli.main(["csv-download"]) == 0


def test_csv_import_no_refresh(
    cli_db: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, Any] = {}

    def fake(db, **kwargs):
        captured.update(kwargs)
        return csv_sync.CsvReport(status="applied")

    monkeypatch.setattr(cli.csv_sync, "run", fake)

    assert cli.main(["csv-import", "--no-refresh"]) == 0
    assert captured["refresh"] is False
    assert captured["leagues"] is None
    assert "Import CSV" in capsys.readouterr().out


def test_csv_download_only_accepts_csv_leagues(cli_db: None) -> None:
    # La Ligue des champions n'a pas de fichier CSV : elle est refusée ici.
    with pytest.raises(SystemExit) as error:
        cli.main(["csv-download", "--leagues", "ucl"])
    assert error.value.code == 2


def test_odds_preview_costs_nothing(
    cli_db: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli.odds_sync, "preview", lambda db, **kw: odds_sync.PreviewReport()
    )

    def interdit(*args, **kwargs):
        raise AssertionError("odds-preview ne doit jamais importer")

    monkeypatch.setattr(cli.odds_sync, "run", interdit)

    assert cli.main(["odds-preview"]) == 0
    assert "aucun crédit consommé" in capsys.readouterr().out


def test_odds_preview_missing_key_fails(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli.odds_sync,
        "preview",
        lambda db, **kw: odds_sync.PreviewReport(
            status="failed", error="Clé The Odds API absente."
        ),
    )

    assert cli.main(["odds-preview"]) == 1


def test_odds_import_uses_extended_options(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake(db, **kwargs):
        captured.update(kwargs)
        return _odds_report("applied", credits=4)

    monkeypatch.setattr(cli.odds_sync, "run", fake)

    assert cli.main(["odds-import", "--no-extended", "--extended-limit", "3"]) == 0
    assert captured["include_extended"] is False
    assert captured["extended_limit"] == 3


def test_facts_json_is_valid(
    cli_db: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.facts, "run_sync", lambda db, **kw: _facts_report("applied"))

    assert cli.main(["facts", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "applied"
    assert "totals" in payload


def _facts_overview() -> dict[str, Any]:
    return {
        "provider": "bigballsdata",
        "configured": True,
        "season": "2026",
        "quota": {"used": 25, "remaining": 1775, "limit": 1800, "reset_at": None},
        "totals": {"matches": 2314, "teams": 200, "stats_rows": 1000, "xg_rows": 992},
        "leagues": [],
        "runs": ["objet ORM non sérialisable"],
    }


def _csv_overview() -> dict[str, Any]:
    return {
        "provider": "football_data_uk",
        "configured": True,
        "directory": "data/local/csv",
        "season": "2026-2027",
        "files": [],
        "totals": {
            "files": 5,
            "rows": 500,
            "matches_covered": 496,
            "xg_rows": 992,
            "links_applied": 496,
            "links_pending": 4,
            "closing_markets": 992,
            "closing_rows": 2480,
        },
        "coverage": [],
        "pending": [],
        "last_run": None,
    }


def _odds_overview() -> dict[str, Any]:
    return {
        "provider": "the_odds_api",
        "configured": True,
        "quota": {"used": 10, "remaining": 390, "limit": 400, "reset_at": None},
        "costs": {},
        "totals": {"markets": 992, "odds_rows": 2480, "active_links": 50},
        "upcoming": {},
        "last_run": None,
    }


class _ReadOnlySession:
    """Session qui refuse toute écriture : status doit rester en lecture."""

    def __init__(self) -> None:
        self.closed = False

    def commit(self) -> None:
        raise AssertionError("status ne doit jamais écrire en base")

    def rollback(self) -> None:
        raise AssertionError("status ne doit jamais annuler de transaction")

    def close(self) -> None:
        self.closed = True


def test_status_is_read_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    session = _ReadOnlySession()
    monkeypatch.setattr(cli, "SessionLocal", lambda: session)
    monkeypatch.setattr(cli.facts, "overview", lambda db: _facts_overview())
    monkeypatch.setattr(cli.csv_sync, "overview", lambda db: _csv_overview())
    monkeypatch.setattr(cli.odds_sync, "overview", lambda db: _odds_overview())
    monkeypatch.setattr(cli.auto_sync, "is_due", lambda db: False)
    monkeypatch.setattr(cli.auto_sync, "last_applied_at", lambda db: None)
    monkeypatch.setattr(cli.auto_sync, "last_run", lambda db: None)

    assert cli.main(["status"]) == 0
    assert session.closed is True
    sortie = capsys.readouterr().out
    assert "BigBallsData" in sortie
    assert "Mise à jour automatique" in sortie


def test_status_json_contains_no_secret(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    session = _ReadOnlySession()
    monkeypatch.setattr(cli, "SessionLocal", lambda: session)
    monkeypatch.setattr(cli.facts, "overview", lambda db: _facts_overview())
    monkeypatch.setattr(cli.csv_sync, "overview", lambda db: _csv_overview())
    monkeypatch.setattr(cli.odds_sync, "overview", lambda db: _odds_overview())
    monkeypatch.setattr(cli.auto_sync, "is_due", lambda db: True)
    monkeypatch.setattr(cli.auto_sync, "last_applied_at", lambda db: None)
    monkeypatch.setattr(cli.auto_sync, "last_run", lambda db: None)
    monkeypatch.setattr(settings, "bigballsdata_key", "cle-secrete-bbd")
    monkeypatch.setattr(settings, "the_odds_api_key", "cle-secrete-odds")

    assert cli.main(["status", "--json"]) == 0

    sortie = capsys.readouterr().out
    payload = json.loads(sortie)
    assert payload["auto_sync"]["due"] is True
    assert "objet ORM non sérialisable" not in sortie
    assert "cle-secrete-bbd" not in sortie
    assert "cle-secrete-odds" not in sortie


class _SessionSpy:
    def __init__(self) -> None:
        self.rolled_back = 0
        self.closed = False

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        self.rolled_back += 1

    def close(self) -> None:
        self.closed = True


def test_unexpected_error_rolls_back_and_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    session = _SessionSpy()
    monkeypatch.setattr(cli, "SessionLocal", lambda: session)

    def boom(db, **kwargs):
        raise RuntimeError("connexion refusée")

    monkeypatch.setattr(cli.facts, "run_sync", boom)

    assert cli.main(["facts"]) == 1
    assert session.rolled_back == 1
    assert session.closed is True
    assert "Échec" in capsys.readouterr().err
