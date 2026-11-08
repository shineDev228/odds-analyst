"""Tests des marchés, sélections et relevés de cotes."""

import pytest
from fastapi.testclient import TestClient

RESULT_ODDS = {"1": 2.0, "X": 3.5, "2": 3.6}


def _create_match(auth_client: TestClient, season_id: str, teams: tuple[str, str]) -> dict:
    response = auth_client.post(
        "/api/v1/matches",
        json={
            "season_id": season_id,
            "home_team_id": teams[0],
            "away_team_id": teams[1],
            "kickoff_at": "2026-11-10T20:45:00+01:00",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_result_market(auth_client: TestClient, match_id: str) -> dict:
    response = auth_client.post(
        f"/api/v1/matches/{match_id}/markets",
        json={
            "template_code": "football.resultat_1x2",
            "line": None,
            "selections": [
                {"code": "1", "label": "Domicile", "decimal_odds": RESULT_ODDS["1"]},
                {"code": "X", "label": "Match nul", "decimal_odds": RESULT_ODDS["X"]},
                {"code": "2", "label": "Extérieur", "decimal_odds": RESULT_ODDS["2"]},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_catalog_is_seeded_and_unique(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/markets/catalog", params={"sport_code": "football"})
    assert response.status_code == 200, response.text
    catalog = response.json()
    assert len(catalog) >= 80
    codes = [item["code"] for item in catalog]
    assert len(codes) == len(set(codes))
    assert "football.resultat_1x2" in codes
    assert "football.score_exact" in codes
    assert "football.total_corners" in codes

    families = {item["family"] for item in catalog}
    assert {
        "resultat",
        "double_chance",
        "handicap",
        "totaux",
        "corners",
        "cartons",
        "joueur",
    } <= families


def test_catalog_covers_other_sports(auth_client: TestClient) -> None:
    for sport in ("tennis", "basketball", "hockey_sur_glace", "rugby", "esport"):
        response = auth_client.get("/api/v1/markets/catalog", params={"sport_code": sport})
        assert response.status_code == 200
        assert len(response.json()) >= 3


def test_create_result_market_with_odds(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    match = _create_match(auth_client, season_id, teams)
    market = _create_result_market(auth_client, match["id"])

    assert market["name"] == "Résultat (temps réglementaire)"
    assert market["family"] == "resultat"
    assert market["is_custom"] is False
    assert len(market["selections"]) == 3
    assert market["is_complete"] is True
    assert market["overround_percent"] == pytest.approx(6.3492, rel=1e-3)
    assert market["implied_probability_total"] is not None

    by_code = {item["code"]: item for item in market["selections"]}
    assert by_code["1"]["latest_odds"] == 2.0
    assert by_code["1"]["odds_count"] == 1
    assert by_code["1"]["implied_probability"] == 0.5
    assert by_code["1"]["fair_probability"] is not None
    assert by_code["1"]["fair_odds"] > 2.0  # marge retirée : cote équitable plus élevée
    # Le favori reste favori après normalisation.
    assert by_code["1"]["fair_probability"] > by_code["X"]["fair_probability"]


def test_duplicate_market_is_rejected(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    match = _create_match(auth_client, season_id, teams)
    _create_result_market(auth_client, match["id"])
    response = auth_client.post(
        f"/api/v1/matches/{match['id']}/markets",
        json={"template_code": "football.resultat_1x2"},
    )
    assert response.status_code == 409
    assert "existe déjà" in response.json()["detail"]


def test_team_market_rejects_foreign_team(
    auth_client: TestClient, season_id: str, teams: tuple[str, str], sport_id: str
) -> None:
    match = _create_match(auth_client, season_id, teams)
    other = auth_client.post(
        "/api/v1/teams", json={"sport_id": sport_id, "name": "Équipe Gamma"}
    ).json()
    response = auth_client.post(
        f"/api/v1/matches/{match['id']}/markets",
        json={
            "template_code": "football.total_buts_domicile",
            "subject": "team",
            "subject_team_id": other["id"],
            "line": 1.5,
        },
    )
    assert response.status_code == 409
    assert "l'une des deux équipes" in response.json()["detail"]


def test_team_market_accepts_match_team(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    match = _create_match(auth_client, season_id, teams)
    response = auth_client.post(
        f"/api/v1/matches/{match['id']}/markets",
        json={
            "template_code": "football.total_buts_domicile",
            "subject": "team",
            "subject_team_id": teams[0],
            "line": 1.5,
            "selections": [
                {"code": "plus", "label": "Plus", "decimal_odds": 1.9},
                {"code": "moins", "label": "Moins", "decimal_odds": 1.9},
            ],
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["subject"] == "team"
    assert payload["subject_team_name"] == "Équipe Alpha"


def test_line_is_required_for_line_market(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    match = _create_match(auth_client, season_id, teams)
    response = auth_client.post(
        f"/api/v1/matches/{match['id']}/markets",
        json={"template_code": "football.total_buts"},
    )
    assert response.status_code == 409
    assert "ligne" in response.json()["detail"]


def test_custom_market_without_template(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    match = _create_match(auth_client, season_id, teams)
    response = auth_client.post(
        f"/api/v1/matches/{match['id']}/markets",
        json={
            "name": "Cartons par joueur — variante maison",
            "family": "cartons",
            "period": "match",
            "subject": "player",
            "subject_player": "Joueur Test",
            "selections": [
                {"label": "Plus de 0,5", "decimal_odds": 1.4},
                {"label": "Moins de 0,5", "decimal_odds": 2.8},
            ],
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["is_custom"] is True
    assert payload["template_code"] is None
    assert payload["subject_player"] == "Joueur Test"
    assert {item["code"] for item in payload["selections"]} == {"plus_de_0_5", "moins_de_0_5"}


def test_add_odds_keeps_history(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    match = _create_match(auth_client, season_id, teams)
    market = _create_result_market(auth_client, match["id"])
    home_selection = next(item for item in market["selections"] if item["code"] == "1")

    response = auth_client.post(
        f"/api/v1/markets/{market['id']}/selections/{home_selection['id']}/odds",
        json={"decimal_odds": 1.85, "note": "Cote corrigée"},
    )
    assert response.status_code == 201, response.text
    updated = response.json()
    home = next(item for item in updated["selections"] if item["code"] == "1")
    assert home["latest_odds"] == 1.85
    assert home["odds_count"] == 2
    assert [item["decimal_odds"] for item in home["history"]] == [1.85, 2.0]
    assert updated["is_complete"] is True

    history = auth_client.get(f"/api/v1/markets/{market['id']}/history").json()
    assert len(history) == 4
    assert history[0]["note"] == "Cote corrigée"


def test_invalid_odds_are_rejected(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    match = _create_match(auth_client, season_id, teams)
    market = _create_result_market(auth_client, match["id"])
    selection = market["selections"][0]
    response = auth_client.post(
        f"/api/v1/markets/{market['id']}/selections/{selection['id']}/odds",
        json={"decimal_odds": 1.0},
    )
    assert response.status_code == 422


def test_delete_odds_snapshot(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    match = _create_match(auth_client, season_id, teams)
    market = _create_result_market(auth_client, match["id"])
    selection = market["selections"][0]
    snapshot_id = selection["history"][0]["id"]
    response = auth_client.delete(
        f"/api/v1/markets/{market['id']}/selections/{selection['id']}/odds/{snapshot_id}"
    )
    assert response.status_code == 204
    after = auth_client.get(f"/api/v1/markets/{market['id']}").json()
    assert after["selections"][0]["odds_count"] == 0
    assert after["is_complete"] is False


def test_delete_market_removes_history(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    match = _create_match(auth_client, season_id, teams)
    market = _create_result_market(auth_client, match["id"])
    response = auth_client.delete(f"/api/v1/markets/{market['id']}")
    assert response.status_code == 204
    assert auth_client.get(f"/api/v1/markets/{market['id']}").status_code == 404
    assert auth_client.get(f"/api/v1/matches/{match['id']}/markets").json() == []


def test_markets_require_authentication(
    guest: TestClient, auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    match = _create_match(auth_client, season_id, teams)
    guest.cookies.clear()
    assert guest.get(f"/api/v1/matches/{match['id']}/markets").status_code == 401


def test_market_creation_requires_csrf(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    match = _create_match(auth_client, season_id, teams)
    auth_client.headers.pop("X-CSRF-Token", None)
    response = auth_client.post(
        f"/api/v1/matches/{match['id']}/markets",
        json={"template_code": "football.resultat_1x2"},
    )
    assert response.status_code == 403
