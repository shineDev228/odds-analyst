"""Tests des routes des connecteurs."""

from app.core.config import settings
from app.services import connectors as service
from fastapi.testclient import TestClient


class FakeBigBalls:
    def list_matches(self, **_: object) -> list[dict]:
        return [
            {
                "id": "bbd-1",
                "kickoff_utc": "2026-12-01T20:00:00Z",
                "status": "scheduled",
                "home": {"id": "bbd-h", "name": "Équipe Alpha", "short_name": "EA"},
                "away": {"id": "bbd-a", "name": "Équipe Beta", "short_name": "EB"},
                "score": None,
            }
        ]

    def close(self) -> None:
        return None


def _create_link(
    client: TestClient, competition_id: str, season_id: str, provider: str = "bigballsdata"
) -> dict:
    response = client.post(
        "/api/v1/connectors/links",
        json={
            "provider": provider,
            "competition_id": competition_id,
            "season_id": season_id,
            "external_league_id": "ligue-1",
            "external_season": "2025",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_connectors_require_authentication(guest: TestClient) -> None:
    assert guest.get("/api/v1/connectors").status_code == 401


def test_overview_lists_four_providers(auth_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "bigballsdata_key", "")
    monkeypatch.setattr(settings, "the_odds_api_key", "")
    monkeypatch.setattr(settings, "football_data_key", "")
    response = auth_client.get("/api/v1/connectors")
    assert response.status_code == 200, response.text
    data = response.json()
    assert {item["provider"] for item in data["providers"]} == {
        "bigballsdata",
        "the_odds_api",
        "football_data",
        "football_data_uk",
    }
    configure = {item["provider"]: item["configured"] for item in data["providers"]}
    assert configure["football_data_uk"] is True
    assert all(
        item["configured"] is False
        for item in data["providers"]
        if item["provider"] != "football_data_uk"
    )
    assert len(data["usage"]) == 4
    csv_usage = next(
        item for item in data["usage"] if item["provider"] == "football_data_uk"
    )
    assert csv_usage["limit"] is None
    assert csv_usage["remaining"] is None
    for provider in data["providers"]:
        assert "key" not in provider
        assert "api_key" not in provider


def test_missing_key_is_explicit(
    auth_client: TestClient, competition_id: str, season_id: str, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "the_odds_api_key", "")
    link = _create_link(auth_client, competition_id, season_id, provider="the_odds_api")
    response = auth_client.post(f"/api/v1/connectors/links/{link['id']}/odds/preview")
    assert response.status_code == 503, response.text
    assert "THE_ODDS_API_KEY" in response.json()["detail"]


def test_fixtures_preview_and_apply_through_api(
    auth_client: TestClient, competition_id: str, season_id: str, monkeypatch
) -> None:
    link = _create_link(auth_client, competition_id, season_id)
    monkeypatch.setattr(service, "client_for", lambda *_, **__: FakeBigBalls())

    preview = auth_client.post(f"/api/v1/connectors/links/{link['id']}/fixtures/preview")
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["counts"]["created"] == 1
    assert data["status"] == "preview"
    assert data["operation"] == "fixtures"
    assert len(data["teams_to_create"]) == 2

    applied = auth_client.post(f"/api/v1/connectors/sync-runs/{data['run_id']}/apply")
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"
    assert applied.json()["counts"]["created"] == 1

    replay = auth_client.post(f"/api/v1/connectors/sync-runs/{data['run_id']}/apply")
    assert replay.status_code == 409

    runs = auth_client.get("/api/v1/connectors/sync-runs")
    assert runs.status_code == 200
    assert runs.json()[0]["provider"] == "bigballsdata"


def test_unknown_link_returns_404(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/v1/connectors/links/00000000-0000-0000-0000-000000000000/fixtures/preview"
    )
    assert response.status_code == 404


def test_link_can_be_disabled_and_deleted(
    auth_client: TestClient, competition_id: str, season_id: str
) -> None:
    link = _create_link(auth_client, competition_id, season_id)
    patched = auth_client.patch(
        f"/api/v1/connectors/links/{link['id']}", json={"is_enabled": False}
    )
    assert patched.status_code == 200
    assert patched.json()["is_enabled"] is False

    deleted = auth_client.delete(f"/api/v1/connectors/links/{link['id']}")
    assert deleted.status_code == 204
    assert auth_client.get("/api/v1/connectors/links").json() == []


def test_odds_events_route_requires_key(
    auth_client: TestClient, competition_id: str, season_id: str, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "the_odds_api_key", "")
    link = _create_link(auth_client, competition_id, season_id, provider="the_odds_api")
    response = auth_client.post(f"/api/v1/connectors/links/{link['id']}/odds/events")
    assert response.status_code == 503
