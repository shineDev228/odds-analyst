"""Tests de l'API de calibration (rétro-test walk-forward)."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

END = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)


def _create_match(
    client: TestClient,
    season_id: str,
    home_team_id: str,
    away_team_id: str,
    kickoff_at: datetime,
) -> str:
    response = client.post(
        "/api/v1/matches",
        json={
            "season_id": season_id,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "kickoff_at": kickoff_at.isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _add_result(
    client: TestClient,
    season_id: str,
    home_team_id: str,
    away_team_id: str,
    kickoff_at: datetime,
    home_score: int,
    away_score: int,
) -> str:
    match_id = _create_match(client, season_id, home_team_id, away_team_id, kickoff_at)
    response = client.patch(
        f"/api/v1/matches/{match_id}",
        json={"status": "termine", "home_score": home_score, "away_score": away_score},
    )
    assert response.status_code == 200, response.text
    return match_id


def _seed_history(
    client: TestClient,
    season_id: str,
    teams: tuple[str, str],
    *,
    count: int,
    end: datetime = END,
) -> list[tuple[str, str, str]]:
    home, away = teams
    created: list[tuple[str, str, str]] = []
    for index in range(count):
        kickoff = end - timedelta(days=7 * (count - index))
        if index % 2 == 0:
            match_id = _add_result(client, season_id, home, away, kickoff, 2, 1)
            created.append((match_id, home, away))
        else:
            match_id = _add_result(client, season_id, away, home, kickoff, 1, 1)
            created.append((match_id, away, home))
    return created


def test_calibration_requires_authentication(guest: TestClient) -> None:
    response = guest.get("/api/v1/predictions/calibration")
    assert response.status_code in {401, 403}


def test_calibration_on_empty_base_is_explicit(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/predictions/calibration")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["model_version"] == "football-poisson-v2"
    assert data["matches_evaluated"] == 0
    assert data["brier"] is None
    assert data["log_loss"] is None
    assert data["bins"] == []
    assert "Aucune rencontre" in data["message"]
    assert "Rétro-test" in data["avertissement"]


def test_calibration_returns_coherent_metrics(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _seed_history(auth_client, season_id, teams, count=10)
    response = auth_client.get("/api/v1/predictions/calibration")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["matches_evaluated"] > 0
    assert data["matches_evaluated"] + data["matches_excluded"] == 10
    assert data["matches_excluded"] > 0
    assert data["home_wins"] + data["draws"] + data["away_wins"] == data["matches_evaluated"]
    assert 0.0 <= data["brier"] <= 2.0
    assert data["log_loss"] >= 0.0
    assert 0.0 <= data["accuracy"] <= 1.0
    assert data["baseline_brier"] is not None
    assert len(data["bins"]) == 10
    assert sum(item["count"] for item in data["bins"]) == 3 * data["matches_evaluated"]
    assert data["period_start"] <= data["period_end"]
    assert data["period_end"] <= datetime.now(UTC).isoformat()
    assert "rencontre(s) évaluée(s)" in data["message"]


def test_calibration_rejects_out_of_range_limit(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _seed_history(auth_client, season_id, teams, count=4)
    assert auth_client.get("/api/v1/predictions/calibration?limit=5").status_code == 422
    assert auth_client.get("/api/v1/predictions/calibration?limit=101").status_code == 422
    assert auth_client.get("/api/v1/predictions/calibration?limit=10").status_code == 200


def test_calibration_applies_limit(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _seed_history(auth_client, season_id, teams, count=20)
    response = auth_client.get("/api/v1/predictions/calibration?limit=10")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["limit"] == 10
    assert data["matches_evaluated"] + data["matches_excluded"] == 10


def test_calibration_ignores_matches_not_yet_played(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    home, away = teams
    _seed_history(auth_client, season_id, teams, count=6)
    future = datetime.now(UTC) + timedelta(days=60)
    _add_result(auth_client, season_id, home, away, future, 9, 0)

    response = auth_client.get("/api/v1/predictions/calibration")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["matches_evaluated"] + data["matches_excluded"] == 6


def test_calibration_exposes_xg_coverage(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    home, _away = teams
    history = _seed_history(auth_client, season_id, teams, count=8)
    for match_id, home_team_id, away_team_id in history:
        if home_team_id == home:
            home_xg, away_xg = 1.5, 1.0
        else:
            home_xg, away_xg = 1.0, 1.5
        response = auth_client.put(
            f"/api/v1/matches/{match_id}/stats",
            json=[
                {"team_id": home_team_id, "is_home": True, "expected_goals": home_xg},
                {"team_id": away_team_id, "is_home": False, "expected_goals": away_xg},
            ],
        )
        assert response.status_code == 200, response.text

    data = auth_client.get("/api/v1/predictions/calibration").json()
    assert data["mean_xg_coverage"] is not None
    assert 0.0 <= data["mean_xg_coverage"] <= 1.0
