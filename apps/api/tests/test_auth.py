"""Tests d'authentification, de session et de protection CSRF."""

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def test_status_before_bootstrap(guest: TestClient) -> None:
    response = guest.get("/api/v1/auth/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["admin_configured"] is False
    assert payload["authenticated"] is False
    assert payload["user"] is None


def test_bootstrap_creates_admin_and_logs_in(guest: TestClient) -> None:
    response = guest.post(
        "/api/v1/auth/bootstrap",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 201
    assert response.json()["email"] == ADMIN_EMAIL

    status = guest.get("/api/v1/auth/status").json()
    assert status["admin_configured"] is True
    assert status["authenticated"] is True


def test_bootstrap_twice_is_rejected(guest: TestClient) -> None:
    guest.post("/api/v1/auth/bootstrap", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    response = guest.post(
        "/api/v1/auth/bootstrap",
        json={"email": "autre@oddsanalyst.fr", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 409
    assert "existe déjà" in response.json()["detail"]


def test_bootstrap_rejects_weak_password(guest: TestClient) -> None:
    response = guest.post(
        "/api/v1/auth/bootstrap",
        json={"email": ADMIN_EMAIL, "password": "court"},
    )
    assert response.status_code == 422
    messages = [item["message"] for item in response.json()["errors"]]
    assert any("12 caractères" in message for message in messages)


def test_bootstrap_rejects_invalid_email(guest: TestClient) -> None:
    response = guest.post(
        "/api/v1/auth/bootstrap",
        json={"email": "pas-un-email", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_login_and_logout(auth_client: TestClient) -> None:
    assert auth_client.get("/api/v1/auth/me").status_code == 200

    response = auth_client.post("/api/v1/auth/logout")
    assert response.status_code == 204

    assert auth_client.get("/api/v1/auth/me").status_code == 401


def test_login_with_wrong_password(auth_client: TestClient) -> None:
    auth_client.post("/api/v1/auth/logout")
    response = auth_client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": "MauvaisMotDePasse1"},
    )
    assert response.status_code == 401
    assert "incorrect" in response.json()["detail"]


def test_login_rate_limited(guest: TestClient) -> None:
    guest.post("/api/v1/auth/bootstrap", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    for _ in range(5):
        guest.post(
            "/api/v1/auth/login",
            json={"email": ADMIN_EMAIL, "password": "MauvaisMotDePasse1"},
        )
    response = guest.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": "MauvaisMotDePasse1"},
    )
    assert response.status_code == 429
    assert "Trop de tentatives" in response.json()["detail"]


def test_csrf_required_on_mutation(auth_client: TestClient) -> None:
    auth_client.headers.pop("X-CSRF-Token")
    response = auth_client.post(
        "/api/v1/competitions",
        json={"sport_id": "00000000-0000-0000-0000-000000000000", "name": "Sans jeton"},
    )
    assert response.status_code == 403
    assert "Jeton de sécurité" in response.json()["detail"]


def test_reads_allowed_without_csrf(auth_client: TestClient) -> None:
    auth_client.headers.pop("X-CSRF-Token")
    assert auth_client.get("/api/v1/sports").status_code == 200


def test_protected_routes_require_authentication(guest: TestClient) -> None:
    for path in ("/api/v1/competitions", "/api/v1/teams", "/api/v1/matches"):
        assert guest.get(path).status_code == 401
