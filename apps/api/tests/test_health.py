"""Tests du point de contrôle de santé (sans dépendre d'une vraie base)."""

from collections.abc import Iterator

from app.db.session import get_db
from app.main import app
from fastapi.testclient import TestClient


class _FakeResult:
    def scalar(self) -> int:
        return 1


class _FakeSession:
    def execute(self, *_args: object, **_kwargs: object) -> _FakeResult:
        return _FakeResult()


def _override_db() -> Iterator[_FakeSession]:
    yield _FakeSession()


def test_health_returns_ok_when_database_reachable() -> None:
    app.dependency_overrides[get_db] = _override_db
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert payload["application"] == "ODDS ANALYST"


def test_openapi_schema_is_served() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"].startswith("ODDS ANALYST")


def test_root_exposes_disclaimer() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "ne place aucun pari" in response.json()["avertissement"]
