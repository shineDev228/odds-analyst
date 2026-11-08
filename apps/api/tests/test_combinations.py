"""Tests de l'API du générateur de combinaisons."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

NOW = datetime.now(UTC).replace(microsecond=0)
TARGET_KICKOFF = NOW + timedelta(days=30)


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
    count: int = 8,
) -> None:
    home, away = teams
    for index in range(count):
        kickoff = TARGET_KICKOFF - timedelta(days=7 * (index + 1))
        if index % 2 == 0:
            _add_result(client, season_id, home, away, kickoff, 2, 1)
        else:
            _add_result(client, season_id, away, home, kickoff, 1, 2)


def _create_result_market(
    client: TestClient,
    match_id: str,
    *,
    odds: float = 8.0,
) -> None:
    response = client.post(
        f"/api/v1/matches/{match_id}/markets",
        json={
            "template_code": "football.resultat_1x2",
            "selections": [
                {"code": "1", "label": "Domicile", "decimal_odds": odds},
                {"code": "X", "label": "Match nul", "decimal_odds": odds},
                {"code": "2", "label": "Extérieur", "decimal_odds": odds},
            ],
        },
    )
    assert response.status_code == 201, response.text


def _playable_matches(
    client: TestClient,
    season_id: str,
    teams: tuple[str, str],
    *,
    count: int = 2,
) -> list[str]:
    _seed_history(client, season_id, teams)
    ids = []
    for index in range(count):
        match_id = _create_match(
            client,
            season_id,
            teams[0],
            teams[1],
            TARGET_KICKOFF + timedelta(hours=index),
        )
        _create_result_market(client, match_id)
        ids.append(match_id)
    return ids


def test_combinations_require_authentication(guest: TestClient) -> None:
    response = guest.post("/api/v1/combinations/generate", json={})
    assert response.status_code in {401, 403}


def test_combinations_return_explicit_empty_response(auth_client: TestClient) -> None:
    response = auth_client.post("/api/v1/combinations/generate", json={})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["combinaisons"] == []
    assert data["matchs_examines"] == 0
    assert "Aucune rencontre à venir" in data["message"]
    assert data["avertissement"]


def test_combinations_are_coherent(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)

    response = auth_client.post(
        "/api/v1/combinations/generate",
        json={"nombre_selections": 2, "cote_min": 50, "cote_max": 100, "limite": 5},
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["parametres"]["nombre_selections"] == 2
    assert data["parametres"]["cote_min"] == 50
    assert data["parametres"]["cote_max"] == 100
    assert data["matchs_disponibles"] == 2
    assert data["selections_disponibles"] == 6
    assert data["combinaisons"]

    for combination in data["combinaisons"]:
        selections = combination["selections"]
        assert len(selections) == 2
        assert len({item["match_id"] for item in selections}) == 2
        assert 50 <= combination["total_odds"] <= 100
        assert combination["total_odds"] == pytest.approx(64.0)
        probability = 1.0
        for item in selections:
            assert item["decimal_odds"] == 8.0
            assert item["low"] <= item["probability"] <= item["high"]
            probability *= item["probability"]
        assert combination["probability"] == pytest.approx(probability)
        assert combination["low"] <= combination["probability"] <= combination["high"]
        assert combination["expected_value"] == pytest.approx(
            combination["probability"] * combination["total_odds"] - 1.0
        )


def test_combinations_apply_preferences(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)

    settings = auth_client.get("/api/v1/settings").json()
    settings.update(
        {
            "nb_selections_defaut": 2,
            "cote_min": 50,
            "cote_max": 100,
            "marches_autorises": ["1X2"],
        }
    )
    assert auth_client.put("/api/v1/settings", json=settings).status_code == 200

    data = auth_client.post("/api/v1/combinations/generate", json={}).json()
    assert data["parametres"]["nombre_selections"] == 2
    assert data["parametres"]["cote_min"] == 50
    assert data["parametres"]["cote_max"] == 100
    assert data["parametres"]["marches_autorises"] == ["1X2"]
    assert data["combinaisons"]


def test_matches_without_history_are_ignored(
    auth_client: TestClient,
    season_id: str,
    teams: tuple[str, str],
    sport_id: str,
) -> None:
    _playable_matches(auth_client, season_id, teams)

    extra_teams = []
    for name in ("Équipe Gamma", "Équipe Delta"):
        response = auth_client.post("/api/v1/teams", json={"sport_id": sport_id, "name": name})
        assert response.status_code == 201, response.text
        extra_teams.append(response.json()["id"])

    ignored_match = _create_match(
        auth_client,
        season_id,
        extra_teams[0],
        extra_teams[1],
        TARGET_KICKOFF + timedelta(days=1),
    )
    _create_result_market(auth_client, ignored_match)

    data = auth_client.post(
        "/api/v1/combinations/generate",
        json={"nombre_selections": 2, "cote_min": 50, "cote_max": 100},
    ).json()
    assert data["matchs_examines"] == 3
    assert data["matchs_disponibles"] == 2
    assert data["matchs_ignores"] == 1
    assert data["combinaisons"]


def test_team_total_markets_are_ignored(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _seed_history(auth_client, season_id, teams)
    valid_match = _create_match(auth_client, season_id, teams[0], teams[1], TARGET_KICKOFF)
    _create_result_market(auth_client, valid_match)

    team_match = _create_match(
        auth_client,
        season_id,
        teams[0],
        teams[1],
        TARGET_KICKOFF + timedelta(hours=1),
    )
    response = auth_client.post(
        f"/api/v1/matches/{team_match}/markets",
        json={
            "template_code": "football.total_buts_domicile",
            "subject": "team",
            "subject_team_id": teams[0],
            "line": 1.5,
            "selections": [
                {"code": "plus", "label": "Plus", "decimal_odds": 8.0},
                {"code": "moins", "label": "Moins", "decimal_odds": 8.0},
            ],
        },
    )
    assert response.status_code == 201, response.text

    data = auth_client.post(
        "/api/v1/combinations/generate",
        json={"nombre_selections": 2, "cote_min": 50, "cote_max": 100},
    ).json()
    assert data["combinaisons"] == []
    assert data["matchs_disponibles"] == 1
    assert data["matchs_ignores"] == 1
    assert "réduisez le nombre de sélections" in data["message"]


def test_combinations_validate_parameters(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/v1/combinations/generate",
        json={"nombre_selections": 2, "cote_min": 100, "cote_max": 50},
    )
    assert response.status_code == 422

    response = auth_client.post(
        "/api/v1/combinations/generate",
        json={"marches_autorises": ["INCONNU"]},
    )
    assert response.status_code == 422

    response = auth_client.post(
        "/api/v1/combinations/generate",
        json={"nombre_selections": 1},
    )
    assert response.status_code == 422


def test_combinations_report_insufficient_matches(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams, count=1)

    data = auth_client.post(
        "/api/v1/combinations/generate",
        json={"nombre_selections": 2, "cote_min": 50, "cote_max": 100},
    ).json()
    assert data["combinaisons"] == []
    assert data["matchs_disponibles"] == 1
    assert "réduisez le nombre de sélections" in data["message"]


def test_combinations_report_impossible_odds_range(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)

    data = auth_client.post(
        "/api/v1/combinations/generate",
        json={"nombre_selections": 2, "cote_min": 500, "cote_max": 1000},
    ).json()
    assert data["combinaisons"] == []
    assert "Élargissez la fourchette" in data["message"]
