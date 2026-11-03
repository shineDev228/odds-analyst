"""Tests du référentiel : sports, compétitions, saisons, équipes."""

from fastapi.testclient import TestClient


def test_sports_seeded(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/sports")
    assert response.status_code == 200
    codes = [item["code"] for item in response.json()]
    assert "football" in codes


def test_create_and_list_competition(auth_client: TestClient, competition_id: str) -> None:
    response = auth_client.get("/api/v1/competitions")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Ligue Test"


def test_duplicate_competition_rejected(
    auth_client: TestClient, sport_id: str, competition_id: str
) -> None:
    response = auth_client.post(
        "/api/v1/competitions",
        json={"sport_id": sport_id, "name": "Ligue Test", "country": "France"},
    )
    assert response.status_code == 409


def test_update_and_delete_competition(auth_client: TestClient, competition_id: str) -> None:
    patch = auth_client.patch(
        f"/api/v1/competitions/{competition_id}", json={"name": "Ligue Renommée"}
    )
    assert patch.status_code == 200
    assert patch.json()["name"] == "Ligue Renommée"

    delete = auth_client.delete(f"/api/v1/competitions/{competition_id}")
    assert delete.status_code == 204

    assert auth_client.get(f"/api/v1/competitions/{competition_id}").status_code == 404


def test_competition_validation_message_is_french(auth_client: TestClient, sport_id: str) -> None:
    response = auth_client.post(
        "/api/v1/competitions", json={"sport_id": sport_id, "name": "A"}
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["title"] == "Données invalides"
    assert payload["errors"][0]["champ"] == "name"
    assert "trop court" in payload["errors"][0]["message"]


def test_season_dates_validation(auth_client: TestClient, competition_id: str) -> None:
    response = auth_client.post(
        "/api/v1/seasons",
        json={
            "competition_id": competition_id,
            "label": "2027-2028",
            "start_date": "2027-08-01",
            "end_date": "2027-05-01",
        },
    )
    assert response.status_code == 422
    messages = [item["message"] for item in response.json()["errors"]]
    assert any("postérieure" in message for message in messages)


def test_duplicate_team_rejected(
    auth_client: TestClient, sport_id: str, teams: tuple[str, str]
) -> None:
    response = auth_client.post(
        "/api/v1/teams", json={"sport_id": sport_id, "name": "Équipe Alpha"}
    )
    assert response.status_code == 409


def test_team_search(auth_client: TestClient, teams: tuple[str, str]) -> None:
    response = auth_client.get("/api/v1/teams", params={"search": "Beta"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Équipe Beta"


def test_delete_team_used_in_match_is_blocked(
    auth_client: TestClient,
    season_id: str,
    teams: tuple[str, str],
) -> None:
    home_id, away_id = teams
    created = auth_client.post(
        "/api/v1/matches",
        json={
            "season_id": season_id,
            "home_team_id": home_id,
            "away_team_id": away_id,
            "kickoff_at": "2026-11-10T20:45:00+01:00",
        },
    )
    assert created.status_code == 201, created.text

    response = auth_client.delete(f"/api/v1/teams/{home_id}")
    assert response.status_code == 409
    assert "rencontres" in response.json()["detail"]
