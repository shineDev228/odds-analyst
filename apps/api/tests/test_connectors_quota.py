"""Tests des budgets locaux et de la traduction des erreurs HTTP."""

import httpx
import pytest
from app.connectors.base import (
    BudgetExceededError,
    ConnectorError,
    ProviderAuthError,
    ProviderPayloadError,
    ProviderRateLimitError,
)
from app.connectors.http import HttpClient, redact
from app.connectors.quota import consume, ensure_budget, remaining, snapshot
from app.core.config import settings


def test_budget_refuses_before_overspend(engine) -> None:
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        assert remaining(db, "the_odds_api") == settings.the_odds_api_monthly_budget
        ensure_budget(db, "the_odds_api", 2)
        consume(db, "the_odds_api", 2)
        assert remaining(db, "the_odds_api") == settings.the_odds_api_monthly_budget - 2
        with pytest.raises(BudgetExceededError):
            ensure_budget(db, "the_odds_api", settings.the_odds_api_monthly_budget)
        info = snapshot(db, "the_odds_api")
        assert info.used == 2
        assert info.reset_at is not None


def test_redaction_masks_keys() -> None:
    text = "GET /odds?apiKey=secret-value&regions=eu"
    assert "secret-value" not in redact(text)
    assert "apiKey=***" in redact(text)


def _transport(status: int, payload: object | None = None) -> httpx.MockTransport:
    def handler(_: httpx.Request) -> httpx.Response:
        if payload is None:
            return httpx.Response(status, text="not json")
        return httpx.Response(status, json=payload, headers={"x-requests-remaining": "12"})

    return httpx.MockTransport(handler)


def test_http_translates_auth_and_rate_limit() -> None:
    with HttpClient(transport=_transport(401)) as client, pytest.raises(ProviderAuthError):
        client.get_json("https://example.test/a", provider="test")
    with HttpClient(transport=_transport(429)) as client, pytest.raises(ProviderRateLimitError):
        client.get_json("https://example.test/a", provider="test")


def test_http_translates_payload_error() -> None:
    with HttpClient(transport=_transport(200)) as client, pytest.raises(ProviderPayloadError):
        client.get_json("https://example.test/a", provider="test")


def test_http_retries_server_errors_then_succeeds() -> None:
    calls: list[int] = []

    def handler(_: httpx.Request) -> httpx.Response:
        calls.append(1)
        headers = {"x-requests-remaining": "12"}
        if len(calls) == 1:
            return httpx.Response(500, headers=headers)
        return httpx.Response(200, json={"ok": True}, headers=headers)

    sleeps: list[float] = []
    with HttpClient(
        transport=httpx.MockTransport(handler), sleep=sleeps.append, max_retries=2
    ) as client:
        payload, headers = client.get_json("https://example.test/a", provider="test")
    assert payload == {"ok": True}
    assert len(calls) == 2
    assert sleeps == [0.5]
    assert headers["x-requests-remaining"] == "12"


def test_http_does_not_retry_client_errors() -> None:
    calls: list[int] = []

    def handler(_: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(404)

    with HttpClient(
        transport=httpx.MockTransport(handler), max_retries=2
    ) as client, pytest.raises(ConnectorError):
        client.get_json("https://example.test/a", provider="test")
    assert len(calls) == 1
