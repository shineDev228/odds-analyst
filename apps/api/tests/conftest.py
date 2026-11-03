"""Fixtures de test : base SQLite en mémoire et client authentifié."""

from collections.abc import Iterator

import app.models
import pytest
from app.db.base import Base
from app.db.seed import seed_defaults
from app.db.session import get_db
from app.main import app
from app.services.auth import limiter
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

ADMIN_EMAIL = "admin@oddsanalyst.fr"
ADMIN_PASSWORD = "MotDePasseSolide2026"


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Iterator[None]:
    limiter._entries.clear()
    yield
    limiter._entries.clear()


@pytest.fixture()
def engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client(session_factory) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded(engine) -> None:
    with Session(engine) as db:
        seed_defaults(db)


@pytest.fixture()
def guest(client: TestClient, seeded: None) -> TestClient:
    """Client non authentifié, sur une base vierge."""
    return client


@pytest.fixture()
def auth_client(client: TestClient, seeded: None) -> TestClient:
    """Client authentifié avec le jeton CSRF positionné."""
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 201, response.text
    csrf = client.cookies.get("odds_analyst_csrf")
    assert csrf
    client.headers["X-CSRF-Token"] = csrf
    return client


@pytest.fixture()
def sport_id(auth_client: TestClient) -> str:
    response = auth_client.get("/api/v1/sports")
    assert response.status_code == 200
    return response.json()[0]["id"]


@pytest.fixture()
def competition_id(auth_client: TestClient, sport_id: str) -> str:
    response = auth_client.post(
        "/api/v1/competitions",
        json={"sport_id": sport_id, "name": "Ligue Test", "country": "France", "tier": 1},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture()
def season_id(auth_client: TestClient, competition_id: str) -> str:
    response = auth_client.post(
        "/api/v1/seasons",
        json={"competition_id": competition_id, "label": "2026-2027"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture()
def teams(auth_client: TestClient, sport_id: str) -> tuple[str, str]:
    ids = []
    for name in ("Équipe Alpha", "Équipe Beta"):
        response = auth_client.post("/api/v1/teams", json={"sport_id": sport_id, "name": name})
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    return ids[0], ids[1]
