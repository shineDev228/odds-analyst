"""Tests de l'API de prédiction statistique."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

TARGET_KICKOFF = datetime(2026, 12, 15, 20, 0, tzinfo=UTC)


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
    *,
    status_value: str = "termine",
) -> str:
    match_id = _create_match(client, season_id, home_team_id, away_team_id, kickoff_at)
    response = client.patch(
        f"/api/v1/matches/{match_id}",
        json={
            "status": status_value,
            "home_score": home_score,
            "away_score": away_score,
        },
    )
    assert response.status_code == 200, response.text
    return match_id


def _seed_history(
    client: TestClient,
    season_id: str,
    teams: tuple[str, str],
    *,
    count: int = 6,
    home_goals: int = 2,
    away_goals: int = 1,
) -> list[tuple[str, str, str]]:
    home, away = teams
    created: list[tuple[str, str, str]] = []
    for index in range(count):
        kickoff = TARGET_KICKOFF - timedelta(days=7 * (index + 1))
        if index % 2 == 0:
            match_id = _add_result(client, season_id, home, away, kickoff, home_goals, away_goals)
            created.append((match_id, home, away))
        else:
            match_id = _add_result(client, season_id, away, home, kickoff, away_goals, home_goals)
            created.append((match_id, away, home))
    return created


def test_prediction_requires_authentication(guest: TestClient) -> None:
    response = guest.get("/api/v1/matches/00000000-0000-0000-0000-000000000000/prediction")
    assert response.status_code in {401, 403}


def test_prediction_rejects_insufficient_history(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    home, away = teams
    target = _create_match(auth_client, season_id, home, away, TARGET_KICKOFF)
    _seed_history(auth_client, season_id, teams, count=2)
    response = auth_client.get(f"/api/v1/matches/{target}/prediction")
    assert response.status_code == 409
    assert "Historique insuffisant" in response.json()["detail"]
    assert "au moins 3" in response.json()["detail"]


def test_prediction_returns_coherent_probabilities(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    home, away = teams
    target = _create_match(auth_client, season_id, home, away, TARGET_KICKOFF)
    _seed_history(auth_client, season_id, teams, count=8)

    response = auth_client.get(f"/api/v1/matches/{target}/prediction")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["model_version"] == "football-poisson-v2"
    assert data["expected_goals_home"] > 0
    assert data["expected_goals_away"] > 0
    assert data["expected_goals_total"] == pytest.approx(
        data["expected_goals_home"] + data["expected_goals_away"]
    )

    assert sum(item["probability"] for item in data["resultat"]) == pytest.approx(1.0)
    for item in data["resultat"]:
        assert item["low"] <= item["probability"] <= item["high"]
        assert item["label"]

    assert data["double_chance"][0]["code"] == "1X"
    assert sum(item["probability"] for item in data["btts"]) == pytest.approx(1.0)
    assert len(data["scores_exacts"]) == 8
    for total in data["totaux"]:
        assert total["over"]["probability"] + total["under"]["probability"] == pytest.approx(1.0)
        assert total["over"]["low"] <= total["over"]["probability"] <= total["over"]["high"]

    assert data["quality"]["label"]
    assert data["quality"]["matches_home"] == 8
    assert data["quality"]["matches_away"] == 8
    assert data["sources"]["home"]["matches"] == 8
    assert data["sources"]["home"]["method"] == "buts"
    assert data["sources"]["home"]["xg_coverage"] == 0.0
    assert data["sources"]["home"]["goals_only_matches"] == 8
    assert -0.20 <= data["config"]["dixon_coles_rho"] <= 0.15
    assert data["config"]["xg_weight"] == pytest.approx(0.5)
    assert any("Modèle v2" in warning for warning in data["quality"]["warnings"])
    assert "aucun résultat" in data["avertissement"]


def test_batch_predictions_match_individual_ones(
    auth_client: TestClient, session_factory, season_id: str, teams: tuple[str, str]
) -> None:
    """Le chargement partagé doit produire exactement les mêmes pronostics."""
    from uuid import UUID

    from app.models.match import Match
    from app.services.predictions import build_prediction, build_predictions

    home, away = teams
    _seed_history(auth_client, season_id, teams, count=8)
    first_id = _create_match(auth_client, season_id, home, away, TARGET_KICKOFF)
    second_id = _create_match(
        auth_client, season_id, away, home, TARGET_KICKOFF + timedelta(days=7)
    )

    with session_factory() as db:
        first = db.get(Match, UUID(first_id))
        second = db.get(Match, UUID(second_id))
        assert first is not None and second is not None

        single_first = build_prediction(db, first.id)
        single_second = build_prediction(db, second.id)
        batch = build_predictions(db, [first, second])

    assert batch[first.id] is not None and batch[second.id] is not None
    assert batch[first.id].model_dump(exclude={"computed_at"}) == single_first.model_dump(
        exclude={"computed_at"}
    )
    assert batch[second.id].model_dump(exclude={"computed_at"}) == single_second.model_dump(
        exclude={"computed_at"}
    )


def test_prediction_ignores_future_and_unfinished_matches(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    home, away = teams
    target = _create_match(auth_client, season_id, home, away, TARGET_KICKOFF)
    _seed_history(auth_client, season_id, teams, count=2)

    future = TARGET_KICKOFF + timedelta(days=30)
    _add_result(auth_client, season_id, home, away, future, 3, 0)
    _add_result(
        auth_client,
        season_id,
        home,
        away,
        TARGET_KICKOFF - timedelta(days=3),
        3,
        0,
        status_value="programme",
    )
    _add_result(
        auth_client,
        season_id,
        away,
        home,
        TARGET_KICKOFF - timedelta(days=4),
        2,
        0,
        status_value="annule",
    )

    response = auth_client.get(f"/api/v1/matches/{target}/prediction")
    assert response.status_code == 409
    assert "2 match(s) terminé(s)" in response.json()["detail"]


def test_prediction_applies_preferences(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    home, away = teams
    target = _create_match(auth_client, season_id, home, away, TARGET_KICKOFF)
    _seed_history(auth_client, season_id, teams, count=5)

    settings = auth_client.get("/api/v1/settings").json()
    settings["demi_vie_jours"] = 120
    settings["nb_matchs_historique"] = 12
    assert auth_client.put("/api/v1/settings", json=settings).status_code == 200

    data = auth_client.get(f"/api/v1/matches/{target}/prediction").json()
    assert data["config"]["demi_vie_jours"] == 120
    assert data["config"]["nb_matchs_historique"] == 12


def test_prediction_unknown_match_returns_404(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/matches/00000000-0000-0000-0000-000000000000/prediction")
    assert response.status_code == 404


def _set_expected_goals(
    client: TestClient,
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    home_xg: float,
    away_xg: float,
) -> None:
    response = client.put(
        f"/api/v1/matches/{match_id}/stats",
        json=[
            {"team_id": home_team_id, "is_home": True, "expected_goals": home_xg},
            {"team_id": away_team_id, "is_home": False, "expected_goals": away_xg},
        ],
    )
    assert response.status_code == 200, response.text


def test_prediction_uses_entered_xg(
    auth_client: TestClient, season_id: str, teams: tuple[str, str]
) -> None:
    home, away = teams
    target = _create_match(auth_client, season_id, home, away, TARGET_KICKOFF)
    history = _seed_history(auth_client, season_id, teams, count=8)

    baseline = auth_client.get(f"/api/v1/matches/{target}/prediction").json()
    assert baseline["sources"]["home"]["method"] == "buts"

    for match_id, home_team_id, away_team_id in history:
        if home_team_id == home:
            home_xg, away_xg = 3.0, 0.4
        else:
            home_xg, away_xg = 0.4, 3.0
        _set_expected_goals(auth_client, match_id, home_team_id, away_team_id, home_xg, away_xg)

    enriched = auth_client.get(f"/api/v1/matches/{target}/prediction").json()
    assert enriched["sources"]["home"]["xg_matches"] == 8
    assert enriched["sources"]["home"]["method"] == "xg"
    assert enriched["sources"]["home"]["xg_coverage"] == pytest.approx(1.0)
    assert enriched["expected_goals_home"] != baseline["expected_goals_home"]
    assert enriched["model_version"] == "football-poisson-v2"
