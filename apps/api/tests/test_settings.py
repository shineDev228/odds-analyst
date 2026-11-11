"""Tests des paramètres applicatifs."""

from fastapi.testclient import TestClient


def test_defaults(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/settings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["cote_min"] == 50.0
    assert payload["cote_max"] == 100.0
    assert payload["nb_selections_defaut"] == 8
    assert payload["marches_autorises"] == [
        "1X2",
        "DOUBLE_CHANCE",
        "PLUS_MOINS",
        "BTTS",
    ]


def test_update_and_persist(auth_client: TestClient) -> None:
    response = auth_client.put(
        "/api/v1/settings",
        json={
            "cote_min": 60.0,
            "cote_max": 120.0,
            "nb_selections_defaut": 9,
            "marches_autorises": ["1X2", "PLUS_MOINS"],
            "demi_vie_jours": 180,
            "nb_matchs_historique": 30,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["cote_min"] == 60.0

    reread = auth_client.get("/api/v1/settings").json()
    assert reread["cote_max"] == 120.0
    assert reread["nb_selections_defaut"] == 9


def test_inverted_range_rejected(auth_client: TestClient) -> None:
    response = auth_client.put(
        "/api/v1/settings",
        json={
            "cote_min": 150.0,
            "cote_max": 100.0,
            "nb_selections_defaut": 8,
            "marches_autorises": ["1X2"],
            "demi_vie_jours": 240,
            "nb_matchs_historique": 38,
        },
    )
    assert response.status_code == 422
    messages = [item["message"] for item in response.json()["errors"]]
    assert any("supérieure" in message for message in messages)
