"""Tests des rencontres et des statistiques."""

from fastapi.testclient import TestClient


def _create_match(auth_client: TestClient, season_id: str, home: str, away: str) -> dict:
    response = auth_client.post(
        "/api/v1/matches",
        json={
            "season_id": season_id,
            "home_team_id": home,
            "away_team_id": away,
            "kickoff_at": "2026-11-10T20:45:00",
            "venue": "Stade de Test",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_match_normalizes_timezone(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    home, away = teams
    match = _create_match(auth_client, season_id, home, away)
    assert match["kickoff_at"].endswith("Z") or "+00:00" in match["kickoff_at"]
    assert match["status"] == "programme"
    assert match["home_team_name"] == "Équipe Alpha"
    assert match["competition_name"] == "Ligue Test"


def test_match_rejects_same_team(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    home, _ = teams
    response = auth_client.post(
        "/api/v1/matches",
        json={
            "season_id": season_id,
            "home_team_id": home,
            "away_team_id": home,
            "kickoff_at": "2026-11-10T20:45:00+01:00",
        },
    )
    assert response.status_code == 422
    messages = [item["message"] for item in response.json()["errors"]]
    assert any("différentes" in message for message in messages)


def test_update_match_score(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    match = _create_match(auth_client, season_id, *teams)
    response = auth_client.patch(
        f"/api/v1/matches/{match['id']}",
        json={"status": "termine", "home_score": 2, "away_score": 1},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "termine"
    assert payload["home_score"] == 2


def test_list_matches_filters(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _create_match(auth_client, season_id, *teams)

    by_season = auth_client.get("/api/v1/matches", params={"season_id": season_id}).json()
    assert by_season["total"] == 1

    by_team = auth_client.get("/api/v1/matches", params={"team_id": teams[0]}).json()
    assert by_team["total"] == 1

    by_status = auth_client.get("/api/v1/matches", params={"status": "termine"}).json()
    assert by_status["total"] == 0


def _add_1x2_odds(
    client: TestClient,
    match_id: str,
    home: float,
    draw: float,
    away: float,
) -> dict:
    response = client.post(
        f"/api/v1/matches/{match_id}/markets",
        json={
            "template_code": "football.resultat_1x2",
            "selections": [
                {"code": "1", "label": "Domicile", "decimal_odds": home},
                {"code": "X", "label": "Match nul", "decimal_odds": draw},
                {"code": "2", "label": "Extérieur", "decimal_odds": away},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_list_matches_exposes_latest_1x2_odds(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    match = _create_match(auth_client, season_id, *teams)
    market = _add_1x2_odds(auth_client, match["id"], 1.85, 3.4, 4.2)

    payload = auth_client.get("/api/v1/matches", params={"season_id": season_id}).json()
    assert payload["items"][0]["odds_1x2"] == {
        "home": 1.85,
        "draw": 3.4,
        "away": 4.2,
    }

    home_selection = next(item for item in market["selections"] if item["code"] == "1")
    response = auth_client.post(
        f"/api/v1/markets/{market['id']}/selections/{home_selection['id']}/odds",
        json={"decimal_odds": 1.95},
    )
    assert response.status_code == 201, response.text

    payload = auth_client.get("/api/v1/matches", params={"season_id": season_id}).json()
    assert payload["items"][0]["odds_1x2"]["home"] == 1.95
    assert payload["items"][0]["odds_1x2"]["draw"] == 3.4


def test_list_matches_without_odds(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _create_match(auth_client, season_id, *teams)

    payload = auth_client.get("/api/v1/matches", params={"season_id": season_id}).json()
    assert payload["items"][0]["odds_1x2"] is None


def test_stats_upsert(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    home, away = teams
    match = _create_match(auth_client, season_id, home, away)

    payload = [
        {
            "team_id": home,
            "is_home": True,
            "goals_for": 2,
            "goals_against": 1,
            "shots": 14,
            "shots_on_target": 6,
            "possession": 58.5,
            "corners": 7,
            "yellow_cards": 1,
            "red_cards": 0,
            "expected_goals": 1.9,
        },
        {
            "team_id": away,
            "is_home": False,
            "goals_for": 1,
            "goals_against": 2,
            "shots": 9,
            "possession": 41.5,
            "corners": 3,
        },
    ]
    response = auth_client.put(f"/api/v1/matches/{match['id']}/stats", json=payload)
    assert response.status_code == 200, response.text
    assert len(response.json()) == 2

    # Deuxième appel : mise à jour, pas de doublon.
    payload[0]["shots"] = 16
    response = auth_client.put(f"/api/v1/matches/{match['id']}/stats", json=payload)
    assert response.status_code == 200
    stats = {item["team_id"]: item for item in response.json()}
    assert stats[home]["shots"] == 16


def test_stats_reject_wrong_teams(
    auth_client: TestClient, season_id: str, teams: tuple[str, str], sport_id: str
) -> None:
    match = _create_match(auth_client, season_id, *teams)
    other = auth_client.post(
        "/api/v1/teams", json={"sport_id": sport_id, "name": "Équipe Gamma"}
    ).json()

    response = auth_client.put(
        f"/api/v1/matches/{match['id']}/stats",
        json=[
            {"team_id": teams[0], "is_home": True},
            {"team_id": other["id"], "is_home": False},
        ],
    )
    assert response.status_code == 409
    assert "exactement les deux équipes" in response.json()["detail"]


def test_stats_possession_bounds(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    match = _create_match(auth_client, season_id, *teams)
    response = auth_client.put(
        f"/api/v1/matches/{match['id']}/stats",
        json=[
            {"team_id": teams[0], "is_home": True, "possession": 120},
            {"team_id": teams[1], "is_home": False},
        ],
    )
    assert response.status_code == 422


def test_dashboard_summary(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _create_match(auth_client, season_id, *teams)
    response = auth_client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["matches"] == 1
    assert payload["teams"] == 2
    assert payload["competitions"] == 1
    assert "aucun pari" in payload["avertissement"]
