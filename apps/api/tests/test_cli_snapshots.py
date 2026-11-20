"""Tests de la commande ``snapshots`` (phase 14A, étape 5).

Aucun réseau : chaque service est remplacé par une doublure. Les tests portent
sur l'enchaînement des étapes, l'isolation des pannes, les options et les codes
de sortie — jamais sur le contenu des snapshots, déjà couvert par les tests
14A.3 et 14A.4.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from app import cli
from app.core.config import settings
from app.services import csv_sync, snapshots
from app.services import synchronization as facts


@pytest.fixture()
def cli_db(monkeypatch: pytest.MonkeyPatch, session_factory) -> None:
    monkeypatch.setattr(cli, "SessionLocal", session_factory)


def _facts_report(status: str = "applied", standings: int = 158) -> facts.SyncReport:
    return facts.SyncReport(
        status=status,
        leagues=[
            facts.LeagueReport(
                code="ligue1",
                name="Ligue 1",
                status=status,
                standings_written=standings,
            )
        ],
    )


def _downloaded(status: str = "applied") -> csv_sync.CsvDownloadReport:
    return csv_sync.CsvDownloadReport(status=status)


def _imported(status: str = "applied") -> csv_sync.CsvReport:
    return csv_sync.CsvReport(status=status)


def _snapshot(status: str = "applied", slot: str = "morning") -> snapshots.SnapshotReport:
    return snapshots.SnapshotReport(status=status, slot=slot)


class _Recorder:
    """Doublures des quatre services, avec ordre et arguments capturés."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.args: dict[str, dict[str, Any]] = {}
        self.reports: dict[str, Any] = {
            "facts": _facts_report(),
            "download": _downloaded(),
            "import": _imported(),
            "snapshots": _snapshot(),
        }
        self.errors: dict[str, Exception] = {}

    def _run(self, name: str, **kwargs: Any) -> Any:
        self.calls.append(name)
        self.args[name] = kwargs
        error = self.errors.get(name)
        if error is not None:
            raise error
        report = self.reports[name]
        if name == "snapshots":
            report.slot = kwargs["slot"]
            report.facts_standings = kwargs.get("facts_standings", 0)
        return report


def _install(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    recorder = _Recorder()

    def facts_run(db, **kwargs):
        return recorder._run("facts", **kwargs)

    def download(db, **kwargs):
        return recorder._run("download", **kwargs)

    def run(db, **kwargs):
        return recorder._run("import", **kwargs)

    def run_snapshots(db, **kwargs):
        return recorder._run("snapshots", **kwargs)

    monkeypatch.setattr(cli.facts, "run_sync", facts_run)
    monkeypatch.setattr(cli.csv_sync, "download", download)
    monkeypatch.setattr(cli.csv_sync, "run", run)
    monkeypatch.setattr(cli.snapshots, "run_snapshots", run_snapshots)
    return recorder


# --- Analyse des arguments --------------------------------------------------


def test_slot_is_required(cli_db: None) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["snapshots"])
    assert error.value.code == 2


def test_unknown_slot_is_a_usage_error(cli_db: None) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["snapshots", "--slot", "midi"])
    assert error.value.code == 2


def test_unknown_league_is_a_usage_error(cli_db: None) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["snapshots", "--slot", "morning", "--leagues", "ligue1,inconnue"])
    assert error.value.code == 2


def test_evening_without_board_is_a_usage_error(cli_db: None) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["snapshots", "--slot", "evening", "--no-board"])
    assert error.value.code == 2


def test_a_morning_pass_with_every_step_disabled_is_refused(cli_db: None) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "snapshots",
                "--slot",
                "morning",
                "--no-facts",
                "--no-csv",
                "--no-teams",
                "--no-board",
            ]
        )
    assert error.value.code == 2


# --- Passe du matin ---------------------------------------------------------


def test_morning_runs_every_step_in_order(
    cli_db: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = _install(monkeypatch)

    assert cli.main(["snapshots", "--slot", "morning"]) == 0

    assert recorder.calls == ["facts", "download", "import", "snapshots"]
    assert recorder.args["facts"]["include_stats"] is True
    assert recorder.args["facts"]["include_standings"] is True
    assert recorder.args["facts"]["stats_limit"] == cli.SNAPSHOTS_STATS_LIMIT
    assert recorder.args["facts"]["leagues"] is None
    assert recorder.args["download"]["leagues"] is None
    # Les fichiers viennent d'être téléchargés : l'import ne rappelle pas le réseau.
    assert recorder.args["import"]["refresh"] is False
    assert recorder.args["snapshots"]["slot"] == "morning"
    assert recorder.args["snapshots"]["include_teams"] is True
    assert recorder.args["snapshots"]["include_board"] is True
    assert recorder.args["snapshots"]["facts_standings"] == 158

    sortie = capsys.readouterr().out
    assert "Passe du matin — 4 étapes" in sortie
    assert "[1/4] Faits BigBallsData" in sortie
    assert "[4/4] Snapshots BigBallsData" in sortie
    assert "Résultat de la passe du matin : appliqué (code 0)" in sortie


def test_morning_can_skip_facts_and_csv(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _install(monkeypatch)

    assert cli.main(["snapshots", "--slot", "morning", "--no-facts", "--no-csv"]) == 0

    assert recorder.calls == ["snapshots"]
    assert recorder.args["snapshots"]["facts_standings"] == 0


def test_no_teams_keeps_the_board_running(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _install(monkeypatch)

    assert cli.main(["snapshots", "--slot", "morning", "--no-teams"]) == 0

    assert recorder.calls[-1] == "snapshots"
    assert recorder.args["snapshots"]["include_teams"] is False
    assert recorder.args["snapshots"]["include_board"] is True


def test_no_board_keeps_the_teams_running(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _install(monkeypatch)

    assert cli.main(["snapshots", "--slot", "morning", "--no-board"]) == 0

    assert recorder.args["snapshots"]["include_teams"] is True
    assert recorder.args["snapshots"]["include_board"] is False


def test_force_is_forwarded(cli_db: None, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _install(monkeypatch)

    assert cli.main(["snapshots", "--slot", "morning", "--force"]) == 0
    assert recorder.args["snapshots"]["force"] is True


def test_leagues_are_forwarded_to_every_step(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _install(monkeypatch)

    assert cli.main(["snapshots", "--slot", "morning", "--leagues", "ligue1,epl"]) == 0

    for name in ("facts", "download", "import", "snapshots"):
        assert recorder.args[name]["leagues"] == ["ligue1", "epl"]


# --- Passe du soir ----------------------------------------------------------


def test_evening_runs_the_board_only(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _install(monkeypatch)

    assert cli.main(["snapshots", "--slot", "evening"]) == 0

    assert recorder.calls == ["snapshots"]
    assert recorder.args["snapshots"]["slot"] == "evening"
    assert recorder.args["snapshots"]["include_teams"] is False
    assert recorder.args["snapshots"]["include_board"] is True
    assert recorder.args["snapshots"]["facts_standings"] == 0


# --- Isolation des étapes et codes de sortie --------------------------------


def test_a_failed_step_does_not_stop_the_next(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _install(monkeypatch)
    recorder.reports["facts"] = _facts_report(status="failed")

    assert cli.main(["snapshots", "--slot", "morning"]) == 1

    assert recorder.calls == ["facts", "download", "import", "snapshots"]
    assert recorder.args["snapshots"]["facts_standings"] == 0


def test_a_raising_step_becomes_a_failure_without_stopping(
    cli_db: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = _install(monkeypatch)
    recorder.errors["facts"] = RuntimeError("fournisseur injoignable")

    assert cli.main(["snapshots", "--slot", "morning"]) == 1

    assert recorder.calls == ["facts", "download", "import", "snapshots"]
    erreur = capsys.readouterr().err
    assert "Faits BigBallsData" in erreur
    assert "fournisseur injoignable" in erreur


def test_a_failed_download_skips_the_import_only(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _install(monkeypatch)
    recorder.reports["download"] = _downloaded(status="failed")

    assert cli.main(["snapshots", "--slot", "morning"]) == 1

    assert recorder.calls == ["facts", "download", "snapshots"]


def test_partial_wins_over_applied(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _install(monkeypatch)
    recorder.reports["download"] = _downloaded(status="partial")

    assert cli.main(["snapshots", "--slot", "morning"]) == 3
    assert recorder.calls == ["facts", "download", "import", "snapshots"]


def test_failure_wins_over_partial(
    cli_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _install(monkeypatch)
    recorder.reports["download"] = _downloaded(status="failed")
    recorder.reports["snapshots"] = _snapshot(status="partial")

    assert cli.main(["snapshots", "--slot", "morning"]) == 1


# --- Rapport JSON -----------------------------------------------------------


def test_json_lists_every_step_without_secret(
    cli_db: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(settings, "bigballsdata_key", "cle-secrete-snapshots-14a5")
    _install(monkeypatch)

    assert cli.main(["snapshots", "--slot", "morning", "--json"]) == 0

    sortie = capsys.readouterr().out
    payload = json.loads(sortie)
    assert payload["slot"] == "morning"
    assert payload["status"] == "applied"
    assert payload["code"] == 0
    assert [step["etape"] for step in payload["etapes"]] == [
        "Faits BigBallsData",
        "Téléchargement CSV",
        "Import CSV",
        "Snapshots BigBallsData",
    ]
    assert payload["etapes"][3]["rapport"]["classements"] == 158
    assert "cle-secrete-snapshots-14a5" not in sortie


def test_json_reports_a_failed_step(
    cli_db: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = _install(monkeypatch)
    recorder.errors["download"] = RuntimeError("dossier en lecture seule")

    assert cli.main(["snapshots", "--slot", "morning", "--json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["code"] == 1
    etapes = {step["etape"]: step for step in payload["etapes"]}
    assert etapes["Téléchargement CSV"]["status"] == "failed"
    assert "lecture seule" in etapes["Téléchargement CSV"]["rapport"]["error"]
    # L'import est sauté, le reste de la passe continue.
    assert "Import CSV" not in etapes
    assert etapes["Snapshots BigBallsData"]["status"] == "applied"
