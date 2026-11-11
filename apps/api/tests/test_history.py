"""Tests de l'API de l'historique et de la performance."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

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


def _create_result_market(client: TestClient, match_id: str, *, odds: float = 8.0) -> dict:
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
    return response.json()


def _create_btts_market(client: TestClient, match_id: str, *, odds: float = 8.0) -> dict:
    response = client.post(
        f"/api/v1/matches/{match_id}/markets",
        json={
            "template_code": "football.btts",
            "selections": [
                {"code": "oui", "label": "Oui", "decimal_odds": odds},
                {"code": "non", "label": "Non", "decimal_odds": odds},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _playable_matches(
    client: TestClient,
    season_id: str,
    teams: tuple[str, str],
    *,
    count: int = 2,
    odds: float = 8.0,
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
        _create_result_market(client, match_id, odds=odds)
        ids.append(match_id)
    return ids


def _generate(client: TestClient, *, nombre: int = 2) -> dict:
    response = client.post(
        "/api/v1/combinations/generate",
        json={
            "nombre_selections": nombre,
            "cote_min": 50,
            "cote_max": 100,
            "limite": 5,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["combinaisons"], data
    return data


def _save_payload(combinaison: dict, parametres: dict) -> dict:
    return {
        "selections": [
            {
                "match_id": item["match_id"],
                "selection_id": item["selection_id"],
                "decimal_odds": item["decimal_odds"],
            }
            for item in combinaison["selections"]
        ],
        "parametres": parametres,
        "note": "Combinaison de test",
    }


def _save(client: TestClient, combinaison: dict, parametres: dict) -> dict:
    response = client.post(
        "/api/v1/combinations",
        json=_save_payload(combinaison, parametres),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _score_for_label(label: str) -> tuple[int, int]:
    if label == "Domicile":
        return 2, 0
    if label == "Match nul":
        return 1, 1
    if label == "Extérieur":
        return 0, 2
    raise AssertionError(f"Libellé inattendu : {label}")


def _losing_score_for_label(label: str) -> tuple[int, int]:
    if label == "Domicile":
        return 0, 1
    if label == "Match nul":
        return 1, 0
    if label == "Extérieur":
        return 2, 0
    raise AssertionError(f"Libellé inattendu : {label}")


def _finish(
    client: TestClient,
    match_id: str,
    home_score: int,
    away_score: int,
) -> None:
    response = client.patch(
        f"/api/v1/matches/{match_id}",
        json={
            "status": "termine",
            "home_score": home_score,
            "away_score": away_score,
        },
    )
    assert response.status_code == 200, response.text


def _first_market_and_selection(client: TestClient, match_id: str) -> tuple[dict, dict]:
    markets = client.get(f"/api/v1/matches/{match_id}/markets").json()
    assert markets
    market = markets[0]
    assert market["selections"]
    return market, market["selections"][0]


def test_history_requires_authentication(guest: TestClient) -> None:
    assert guest.post("/api/v1/combinations", json={}).status_code in {401, 403}
    assert guest.get("/api/v1/combinations").status_code in {401, 403}
    assert guest.get("/api/v1/combinations/performance").status_code in {401, 403}


def test_save_list_and_performance(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)
    data = _generate(auth_client)
    saved = _save(auth_client, data["combinaisons"][0], data["parametres"])

    assert saved["status"] == "en_attente"
    assert saved["status_label"] == "En attente"
    assert saved["total_odds"] == pytest.approx(64.0)
    assert saved["effective_odds"] == pytest.approx(64.0)
    assert saved["payout_units"] is None
    assert saved["note"] == "Combinaison de test"
    assert len(saved["selections"]) == 2
    assert all(item["status"] == "en_attente" for item in saved["selections"])

    listing = auth_client.get("/api/v1/combinations").json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == saved["id"]

    detail = auth_client.get(f"/api/v1/combinations/{saved['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == saved["id"]

    performance = auth_client.get("/api/v1/combinations/performance").json()
    assert performance["total"] == 1
    assert performance["en_attente"] == 1
    assert performance["reglees"] == 0
    assert performance["roi"] is None
    assert performance["avertissement"]


def test_save_rejects_duplicate(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)
    data = _generate(auth_client)
    payload = _save_payload(data["combinaisons"][0], data["parametres"])

    assert auth_client.post("/api/v1/combinations", json=payload).status_code == 201
    response = auth_client.post("/api/v1/combinations", json=payload)
    assert response.status_code == 409
    assert "déjà enregistrée" in response.json()["detail"]


def test_save_rejects_unknown_odds(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)
    data = _generate(auth_client)
    payload = _save_payload(data["combinaisons"][0], data["parametres"])
    payload["selections"][0]["decimal_odds"] = 9.0

    response = auth_client.post("/api/v1/combinations", json=payload)
    assert response.status_code == 409
    assert "aucun relevé" in response.json()["detail"]


def test_save_rejects_started_match(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)
    data = _generate(auth_client)
    payload = _save_payload(data["combinaisons"][0], data["parametres"])
    match_id = payload["selections"][0]["match_id"]

    response = auth_client.patch(
        f"/api/v1/matches/{match_id}",
        json={"kickoff_at": (NOW - timedelta(hours=1)).isoformat()},
    )
    assert response.status_code == 200, response.text

    response = auth_client.post("/api/v1/combinations", json=payload)
    assert response.status_code == 409
    assert "n'est plus à venir" in response.json()["detail"]


def test_save_rejects_out_of_range(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)
    data = _generate(auth_client)
    parametres = dict(data["parametres"])
    parametres["cote_min"] = 100
    parametres["cote_max"] = 200

    response = auth_client.post(
        "/api/v1/combinations",
        json=_save_payload(data["combinaisons"][0], parametres),
    )
    assert response.status_code == 409
    assert "fourchette" in response.json()["detail"]


def test_save_validates_selection_references(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)
    data = _generate(auth_client)
    payload = _save_payload(data["combinaisons"][0], data["parametres"])

    duplicate = {
        **payload,
        "selections": [
            payload["selections"][0],
            {
                **payload["selections"][1],
                "match_id": payload["selections"][0]["match_id"],
            },
        ],
    }
    assert auth_client.post("/api/v1/combinations", json=duplicate).status_code == 422

    unknown_selection = {
        **payload,
        "selections": [
            {**payload["selections"][0], "selection_id": str(uuid4())},
            payload["selections"][1],
        ],
    }
    response = auth_client.post("/api/v1/combinations", json=unknown_selection)
    assert response.status_code == 409
    assert "Sélection introuvable" in response.json()["detail"]

    unknown_match = {
        **payload,
        "selections": [
            {**payload["selections"][0], "match_id": str(uuid4())},
            payload["selections"][1],
        ],
    }
    response = auth_client.post("/api/v1/combinations", json=unknown_match)
    assert response.status_code == 409
    assert "ne correspond pas" in response.json()["detail"]


def test_save_rejects_unsupported_market(
    auth_client: TestClient,
    season_id: str,
    teams: tuple[str, str],
) -> None:
    matches = _playable_matches(auth_client, season_id, teams, count=3)
    data = _generate(auth_client)
    used = {item["match_id"] for item in data["combinaisons"][0]["selections"]}
    other_match = next(item for item in matches if item not in used)

    response = auth_client.post(
        f"/api/v1/matches/{other_match}/markets",
        json={
            "template_code": "football.total_corners",
            "line": 9.5,
            "selections": [
                {"code": "plus", "label": "Plus", "decimal_odds": 8.0},
                {"code": "moins", "label": "Moins", "decimal_odds": 8.0},
            ],
        },
    )
    assert response.status_code == 201, response.text
    market = response.json()
    selection = next(item for item in market["selections"] if item["code"] == "plus")

    payload = _save_payload(data["combinaisons"][0], data["parametres"])
    payload["selections"][0] = {
        "match_id": other_match,
        "selection_id": selection["id"],
        "decimal_odds": 8.0,
    }
    response = auth_client.post("/api/v1/combinations", json=payload)
    assert response.status_code == 409
    assert "réglable" in response.json()["detail"]


def test_save_rejects_insufficient_history(
    auth_client: TestClient,
    season_id: str,
    teams: tuple[str, str],
    sport_id: str,
) -> None:
    _playable_matches(auth_client, season_id, teams)
    data = _generate(auth_client)

    extra_teams = []
    for name in ("Équipe Gamma", "Équipe Delta"):
        response = auth_client.post(
            "/api/v1/teams", json={"sport_id": sport_id, "name": name}
        )
        assert response.status_code == 201, response.text
        extra_teams.append(response.json()["id"])
    extra_match = _create_match(
        auth_client,
        season_id,
        extra_teams[0],
        extra_teams[1],
        TARGET_KICKOFF + timedelta(days=2),
    )
    market = _create_result_market(auth_client, extra_match)

    payload = _save_payload(data["combinaisons"][0], data["parametres"])
    payload["selections"][0] = {
        "match_id": extra_match,
        "selection_id": market["selections"][0]["id"],
        "decimal_odds": 8.0,
    }
    response = auth_client.post("/api/v1/combinations", json=payload)
    assert response.status_code == 409
    assert "Historique insuffisant" in response.json()["detail"]


def test_settlement_won_and_performance(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)
    data = _generate(auth_client)
    saved = _save(auth_client, data["combinaisons"][0], data["parametres"])

    for item in saved["selections"]:
        home, away = _score_for_label(item["selection_label"])
        _finish(auth_client, item["match_id"], home, away)

    detail = auth_client.get(f"/api/v1/combinations/{saved['id']}").json()
    assert detail["status"] == "gagnee"
    assert all(item["status"] == "gagnee" for item in detail["selections"])
    assert detail["effective_odds"] == pytest.approx(64.0)
    assert detail["payout_units"] == pytest.approx(64.0)
    assert detail["net_units"] == pytest.approx(63.0)

    performance = auth_client.get("/api/v1/combinations/performance").json()
    assert performance["total"] == 1
    assert performance["gagnees"] == 1
    assert performance["reglees"] == 1
    assert performance["taux_reussite"] == pytest.approx(1.0)
    assert performance["unites_engagees"] == pytest.approx(1.0)
    assert performance["unites_retournees"] == pytest.approx(64.0)
    assert performance["resultat_net"] == pytest.approx(63.0)
    assert performance["roi"] == pytest.approx(63.0)


def test_btts_combination_is_saved_and_settled(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _seed_history(auth_client, season_id, teams)
    for index in range(2):
        match_id = _create_match(
            auth_client,
            season_id,
            teams[0],
            teams[1],
            TARGET_KICKOFF + timedelta(hours=index),
        )
        _create_btts_market(auth_client, match_id)

    data = auth_client.post(
        "/api/v1/combinations/generate",
        json={
            "nombre_selections": 2,
            "cote_min": 50,
            "cote_max": 100,
            "marches_autorises": ["BTTS"],
            "limite": 5,
        },
    ).json()
    assert data["combinaisons"], data
    combinaison = data["combinaisons"][0]
    assert {item["market_name"] for item in combinaison["selections"]} == {
        "Les deux équipes marquent"
    }

    saved = _save(auth_client, combinaison, data["parametres"])
    for item in saved["selections"]:
        home, away = (1, 1) if item["selection_label"] == "Oui" else (1, 0)
        _finish(auth_client, item["match_id"], home, away)

    detail = auth_client.get(f"/api/v1/combinations/{saved['id']}").json()
    assert detail["status"] == "gagnee"
    assert all(item["status"] == "gagnee" for item in detail["selections"])
    assert all(item["market_family"] == "btts" for item in detail["selections"])


def test_settlement_lost(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)
    data = _generate(auth_client)
    saved = _save(auth_client, data["combinaisons"][0], data["parametres"])

    first, second = saved["selections"]
    home, away = _losing_score_for_label(first["selection_label"])
    _finish(auth_client, first["match_id"], home, away)
    home, away = _score_for_label(second["selection_label"])
    _finish(auth_client, second["match_id"], home, away)

    detail = auth_client.get(f"/api/v1/combinations/{saved['id']}").json()
    assert detail["status"] == "perdue"
    assert detail["payout_units"] == pytest.approx(0.0)
    assert detail["net_units"] == pytest.approx(-1.0)

    performance = auth_client.get("/api/v1/combinations/performance").json()
    assert performance["perdues"] == 1
    assert performance["taux_reussite"] == pytest.approx(0.0)
    assert performance["resultat_net"] == pytest.approx(-1.0)
    assert performance["roi"] == pytest.approx(-1.0)


def test_settlement_pending_and_refunded(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)
    data = _generate(auth_client)
    saved = _save(auth_client, data["combinaisons"][0], data["parametres"])

    first, second = saved["selections"]
    assert (
        auth_client.patch(
            f"/api/v1/matches/{first['match_id']}", json={"status": "reporte"}
        ).status_code
        == 200
    )
    detail = auth_client.get(f"/api/v1/combinations/{saved['id']}").json()
    assert detail["status"] == "en_attente"
    assert detail["selections"][0]["status"] == "remboursee"

    assert (
        auth_client.patch(
            f"/api/v1/matches/{second['match_id']}", json={"status": "annule"}
        ).status_code
        == 200
    )
    detail = auth_client.get(f"/api/v1/combinations/{saved['id']}").json()
    assert detail["status"] == "remboursee"
    assert detail["payout_units"] == pytest.approx(1.0)
    assert detail["net_units"] == pytest.approx(0.0)

    performance = auth_client.get("/api/v1/combinations/performance").json()
    assert performance["remboursees"] == 1
    assert performance["resultat_net"] == pytest.approx(0.0)
    assert performance["roi"] == pytest.approx(0.0)


def test_settlement_unavailable_after_match_deletion(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)
    data = _generate(auth_client)
    saved = _save(auth_client, data["combinaisons"][0], data["parametres"])

    match_id = saved["selections"][0]["match_id"]
    assert auth_client.delete(f"/api/v1/matches/{match_id}").status_code == 204

    detail = auth_client.get(f"/api/v1/combinations/{saved['id']}").json()
    assert detail["status"] == "indisponible"
    assert detail["selections"][0]["status"] == "indisponible"
    assert "supprimée" in detail["selections"][0]["reason"]


def test_saved_odds_are_frozen(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)
    data = _generate(auth_client)
    saved = _save(auth_client, data["combinaisons"][0], data["parametres"])
    leg = saved["selections"][0]

    response = auth_client.post(
        f"/api/v1/markets/{leg['market_id']}/selections/{leg['selection_id']}/odds",
        json={"decimal_odds": 2.0, "captured_at": NOW.isoformat()},
    )
    assert response.status_code == 201, response.text

    detail = auth_client.get(f"/api/v1/combinations/{saved['id']}").json()
    assert detail["selections"][0]["decimal_odds"] == pytest.approx(8.0)
    assert detail["total_odds"] == pytest.approx(64.0)


def test_status_filters_and_delete(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)
    data = _generate(auth_client)
    saved = _save(auth_client, data["combinaisons"][0], data["parametres"])

    pending = auth_client.get("/api/v1/combinations?statut=en_attente").json()
    assert pending["total"] == 1
    won = auth_client.get("/api/v1/combinations?statut=gagnee").json()
    assert won["total"] == 0

    for item in saved["selections"]:
        home, away = _score_for_label(item["selection_label"])
        _finish(auth_client, item["match_id"], home, away)

    won = auth_client.get("/api/v1/combinations?statut=gagnee").json()
    assert won["total"] == 1
    pending = auth_client.get("/api/v1/combinations?statut=en_attente").json()
    assert pending["total"] == 0

    assert auth_client.get("/api/v1/combinations?statut=invalide").status_code == 422
    assert (
        auth_client.get(f"/api/v1/combinations/{uuid4()}").status_code == 404
    )

    assert auth_client.delete(f"/api/v1/combinations/{saved['id']}").status_code == 204
    listing = auth_client.get("/api/v1/combinations").json()
    assert listing["total"] == 0
    assert auth_client.get(f"/api/v1/combinations/{saved['id']}").status_code == 404


def test_list_pagination(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    _playable_matches(auth_client, season_id, teams)
    data = _generate(auth_client)
    _save(auth_client, data["combinaisons"][0], data["parametres"])

    page = auth_client.get("/api/v1/combinations?page=1&page_size=1").json()
    assert page["total"] == 1
    assert len(page["items"]) == 1
    assert page["page"] == 1
    assert page["page_size"] == 1
