"""Tests de durcissement : en-têtes, expiration et purge des sessions, CSRF."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.core.config import settings
from app.models.user import UserSession
from app.services.auth import purge_expired_sessions
from fastapi.testclient import TestClient
from sqlalchemy import select


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def test_security_headers_on_api(guest: TestClient) -> None:
    response = guest.get("/api/v1/health")
    assert response.status_code == 200

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert "camera=()" in response.headers["Permissions-Policy"]
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert response.headers["X-Request-ID"]


def test_request_id_is_reused_when_provided(guest: TestClient) -> None:
    response = guest.get("/api/v1/health", headers={"X-Request-ID": "essai-123"})
    assert response.headers["X-Request-ID"] == "essai-123"


def test_hsts_absent_without_https(guest: TestClient) -> None:
    response = guest.get("/api/v1/health")
    assert "Strict-Transport-Security" not in response.headers


def test_hsts_present_when_cookie_secure(
    guest: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "cookie_secure", True)
    response = guest.get("/api/v1/health")
    assert "Strict-Transport-Security" in response.headers
    assert f"max-age={settings.hsts_max_age_seconds}" in response.headers[
        "Strict-Transport-Security"
    ]


def test_docs_csp_allows_swagger_assets(guest: TestClient) -> None:
    response = guest.get("/docs")
    assert response.status_code == 200
    assert "cdn.jsdelivr.net" in response.headers["Content-Security-Policy"]


def test_expired_session_is_rejected_and_removed(
    auth_client: TestClient, session_factory
) -> None:
    with session_factory() as db:
        row = db.scalar(select(UserSession))
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    response = auth_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "expirée" in response.json()["detail"]

    with session_factory() as db:
        assert db.scalar(select(UserSession)) is None


def test_idle_session_is_rejected(
    auth_client: TestClient, session_factory
) -> None:
    with session_factory() as db:
        row = db.scalar(select(UserSession))
        row.last_seen_at = datetime.now(UTC) - timedelta(
            seconds=settings.session_idle_seconds + 60
        )
        db.commit()

    response = auth_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "inactivité" in response.json()["detail"]


def test_session_touch_is_throttled(
    auth_client: TestClient, session_factory
) -> None:
    """Une requête rapprochée ne réécrit pas `last_seen_at`."""
    ancien = datetime.now(UTC) - timedelta(seconds=max(1, settings.session_touch_seconds - 5))
    with session_factory() as db:
        row = db.scalar(select(UserSession))
        row.last_seen_at = ancien
        db.commit()

    assert auth_client.get("/api/v1/auth/me").status_code == 200

    with session_factory() as db:
        row = db.scalar(select(UserSession))
        assert abs((_as_utc(row.last_seen_at) - ancien).total_seconds()) < 1


def test_session_touched_after_interval(
    auth_client: TestClient, session_factory
) -> None:
    ancien = datetime.now(UTC) - timedelta(seconds=settings.session_touch_seconds + 30)
    with session_factory() as db:
        row = db.scalar(select(UserSession))
        row.last_seen_at = ancien
        db.commit()

    assert auth_client.get("/api/v1/auth/me").status_code == 200

    with session_factory() as db:
        row = db.scalar(select(UserSession))
        assert (_as_utc(row.last_seen_at) - ancien).total_seconds() > 10


def test_purge_removes_idle_and_expired_sessions(
    auth_client: TestClient, session_factory
) -> None:
    now = datetime.now(UTC)
    with session_factory() as db:
        courant = db.scalar(select(UserSession))
        db.add_all(
            [
                UserSession(
                    token_hash="a" * 64,
                    csrf_hash="b" * 64,
                    user_id=courant.user_id,
                    created_at=now - timedelta(days=2),
                    expires_at=now + timedelta(hours=1),
                    last_seen_at=now - timedelta(seconds=settings.session_idle_seconds + 5),
                ),
                UserSession(
                    token_hash="c" * 64,
                    csrf_hash="d" * 64,
                    user_id=courant.user_id,
                    created_at=now - timedelta(days=2),
                    expires_at=now - timedelta(minutes=1),
                    last_seen_at=now - timedelta(minutes=2),
                ),
            ]
        )
        db.commit()

        assert purge_expired_sessions(db) == 2
        restantes = db.scalars(select(UserSession)).all()
        assert len(restantes) == 1


def test_csrf_required_on_all_mutations(auth_client: TestClient) -> None:
    """Matrice CSRF : aucune écriture n'est acceptée sans double soumission."""
    identifiant = str(uuid4())
    auth_client.headers.pop("X-CSRF-Token")

    requetes = [
        ("POST", "/api/v1/competitions", {"name": "Sans jeton"}),
        ("PATCH", f"/api/v1/competitions/{identifiant}", {"name": "Sans jeton"}),
        ("DELETE", f"/api/v1/competitions/{identifiant}", None),
        ("POST", "/api/v1/teams", {"name": "Sans jeton"}),
        ("PATCH", f"/api/v1/teams/{identifiant}", {"name": "Sans jeton"}),
        ("DELETE", f"/api/v1/teams/{identifiant}", None),
        ("POST", "/api/v1/matches", {}),
        ("PATCH", f"/api/v1/matches/{identifiant}", {}),
        ("DELETE", f"/api/v1/matches/{identifiant}", None),
        ("PUT", "/api/v1/settings", {}),
        ("POST", "/api/v1/connectors/links", {}),
        ("POST", "/api/v1/auth/logout", None),
    ]

    for methode, chemin, corps in requetes:
        reponse = auth_client.request(methode, chemin, json=corps)
        assert reponse.status_code == 403, f"{methode} {chemin} -> {reponse.status_code}"
        assert "Jeton de sécurité" in reponse.json()["detail"]


def test_csrf_rejects_mismatched_token(auth_client: TestClient) -> None:
    auth_client.headers["X-CSRF-Token"] = "mauvais-jeton"
    response = auth_client.post("/api/v1/competitions", json={"name": "Sans jeton"})
    assert response.status_code == 403
    assert "invalide" in response.json()["detail"]
