import asyncio
import hashlib
import json
import logging
import sys
from collections import Counter
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

from app.api.dependencies import (
    get_alert_service,
    get_rolling_metrics_service,
    get_transaction_service,
)
from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.core.request_protection import RequestProtectionMiddleware
from app.core.security import RateLimiter, get_rate_limiter, security_settings
from app.main import app
from app.schemas.transaction import TransactionCreate

pytestmark = pytest.mark.security
TOKENS = {"operator": "o" * 40, "administrator": "a" * 40}


class LocalLimiter:
    def __init__(self):
        self.counts = Counter()
        self.available = True
        self.limit = 100

    def check(self, key, multiplier=1):
        if not self.available:
            raise HTTPException(503, "Request protection is temporarily unavailable")
        self.counts[key] += 1
        if self.counts[key] > self.limit * multiplier:
            raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": "60"})


@pytest.fixture(autouse=True)
def auth_setup():
    previous = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    limiter = LocalLimiter()
    settings = Settings(
        _env_file=None,
        auth_users=[
            {
                "username": role,
                "role": role,
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            }
            for role, token in TOKENS.items()
        ],
    )
    app.dependency_overrides[security_settings] = lambda: settings
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    yield limiter
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def send(method, path, role=None, raise_errors=True, **kwargs):
    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=raise_errors),
            base_url="http://test",
        ) as client:
            headers = kwargs.pop("headers", {})
            if role:
                headers["Authorization"] = "Bearer " + TOKENS[role]
            return await client.request(method, path, headers=headers, **kwargs)

    return asyncio.run(request())


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/transactions"),
        ("GET", "/alerts"),
        ("GET", "/metrics/rolling"),
        ("GET", "/auth/me"),
        ("POST", "/transactions"),
        ("POST", "/alerts/11111111-1111-4111-8111-111111111111/resolve"),
    ],
)
def test_missing_and_invalid_credentials_cannot_access_actions(method, path):
    for headers in ({}, {"Authorization": "Bearer " + "x" * 40}, {"Authorization": "Basic bad"}):
        response = send(method, path, headers=headers, json={})
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


def test_roles_are_assigned_server_side_and_administrator_creates_transactions():
    assert send("GET", "/auth/me", "operator").json() == {
        "username": "operator",
        "role": "operator",
    }
    data = TransactionCreate.model_config["json_schema_extra"]["examples"][0]
    service = Mock()
    service.create.return_value = {
        **data,
        "id": "11111111-1111-4111-8111-111111111111",
        "created_at": "2026-01-01T00:00:00Z",
    }
    app.dependency_overrides[get_transaction_service] = lambda: service
    assert send("POST", "/transactions", "operator", json=data).status_code == 403
    service.create.assert_not_called()
    assert send("POST", "/transactions", "administrator", json=data).status_code == 201


@pytest.mark.parametrize("action", ["acknowledge", "assign", "resolve", "false-positive"])
def test_alert_actor_is_authenticated_not_caller_supplied(action):
    service = Mock()
    # A controlled service error lets us inspect the actual mutation without a DB fixture.
    service.mutate.side_effect = HTTPException(409, "Test workflow conflict")
    app.dependency_overrides[get_alert_service] = lambda: service
    body = {"actor": "spoofed-administrator", "expected_version": 1, "reason": "Reviewed"}
    if action == "assign":
        body["assignee"] = "analyst-2"
    response = send(
        "POST", f"/alerts/11111111-1111-4111-8111-111111111111/{action}", "operator", json=body
    )
    assert response.status_code == 409
    assert service.mutate.call_args.args[2].actor == "operator"


def test_rate_limit_and_fail_closed_redis_outage(auth_setup):
    auth_setup.limit = 1
    assert send("GET", "/auth/me", "operator").status_code == 200
    response = send("GET", "/auth/me", "operator")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    auth_setup.available = False
    assert send("GET", "/auth/me", "administrator").status_code == 503
    assert send("GET", "/health").status_code == 200
    assert send("GET", "/metrics/prometheus").status_code == 200


def test_limiter_redis_failure_is_controlled_and_identity_is_hashed():
    limiter = RateLimiter(Settings(_env_file=None))
    limiter.redis = Mock()
    limiter.redis.eval.side_effect = RedisConnectionError("password=do-not-leak")
    with pytest.raises(HTTPException) as error:
        limiter.check("operator-sensitive")
    assert error.value.status_code == 503
    assert "do-not-leak" not in str(error.value)
    assert "operator-sensitive" not in limiter.redis.eval.call_args.args[2]


@pytest.mark.parametrize(
    "exception",
    [
        OperationalError(
            "SELECT secret", {"pan": "4111111111111111"}, Exception("password=secret")
        ),
        RedisConnectionError("token=secret"),
    ],
)
def test_dependency_failures_return_sanitized_503(exception):
    def failure():
        raise exception

    app.dependency_overrides[get_rolling_metrics_service] = failure
    response = send("GET", "/metrics/rolling", "operator")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_unavailable"
    assert "secret" not in response.text and "4111111111111111" not in response.text


def test_cors_security_headers_and_body_limits():
    response = send(
        "OPTIONS",
        "/transactions",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    response = send(
        "OPTIONS",
        "/transactions",
        headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    response = send("POST", "/transactions", content=b"x" * 65537)
    assert response.status_code == 413
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert (
        send(
            "POST", "/transactions", content=b"x", headers={"Content-Encoding": "gzip"}
        ).status_code
        == 415
    )


def test_chunked_body_limits_and_slow_upload_deadline():
    async def check(slow):
        async def endpoint(*args):
            pytest.fail("Oversized/slow body reached the application")

        middleware = RequestProtectionMiddleware(endpoint, max_bytes=4, body_timeout=0.01)
        messages = []

        async def receive():
            if slow:
                await asyncio.sleep(1)
            return {"type": "http.request", "body": b"123", "more_body": True}

        async def output(message):
            messages.append(message)

        await middleware(
            {"type": "http", "path": "/transactions", "scheme": "https", "headers": []},
            receive,
            output,
        )
        assert messages[0]["status"] == (408 if slow else 413)
        assert (b"strict-transport-security", b"max-age=31536000") in messages[0]["headers"]

    asyncio.run(check(False))
    asyncio.run(check(True))


def test_logs_redact_payment_data_credentials_and_exception_parameters(monkeypatch):
    monkeypatch.setenv("CUSTOM_SECRET", "exact-private-value")
    try:
        raise RuntimeError("arbitrary-secret exception text 4111111111111111")
    except RuntimeError:
        record = logging.LogRecord(
            "app.test",
            logging.ERROR,
            __file__,
            1,
            "pan=4111-1111-1111-1111 cvv=123 Authorization=Bearer abcdef "
            "password=private exact-private-value",
            (),
            sys.exc_info(),
        )
    record.transaction_id = "11111111-1111-4111-8111-111111111111"
    value = JsonFormatter().format(record)
    for secret in (
        "4111-1111",
        "123",
        "abcdef",
        "password=private",
        "exact-private-value",
        "arbitrary-secret",
    ):
        assert secret not in value
    assert json.loads(value)["transaction_id"] == record.transaction_id


def test_auth_configuration_rejects_ambiguous_roles_and_credentials():
    with pytest.raises(ValueError):
        Settings(
            _env_file=None, auth_users=[{"username": "x", "role": "root", "token_sha256": "a" * 64}]
        )
    with pytest.raises(ValueError) as invalid_secret:
        Settings(
            _env_file=None,
            auth_users=[
                {
                    "username": "a",
                    "role": "operator",
                    "token_sha256": "private-configuration-secret",
                }
            ],
        )
    assert "private-configuration-secret" not in str(invalid_secret.value)
    with pytest.raises(ValueError):
        Settings(_env_file=None, cors_origins=["*"])
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            auth_users=[
                {"username": "a", "role": "operator", "token_sha256": "a" * 64},
                {"username": "b", "role": "administrator", "token_sha256": "a" * 64},
            ],
        )


def test_payment_fields_are_rejected_without_echoing_card_data():
    body = dict(TransactionCreate.model_config["json_schema_extra"]["examples"][0])
    body.update({"card_number": "4111111111111111", "cvv": "123"})
    app.dependency_overrides[get_transaction_service] = lambda: Mock()
    response = send("POST", "/transactions", "administrator", json=body)
    assert response.status_code == 422
    assert "4111111111111111" not in response.text and "123" not in response.text


def test_unexpected_errors_have_controlled_body_headers_and_correlation():
    def failure():
        raise RuntimeError("private exception card_number=4111111111111111")

    app.dependency_overrides[get_rolling_metrics_service] = failure
    response = send(
        "GET",
        "/metrics/rolling",
        "operator",
        raise_errors=False,
        headers={"Origin": "http://localhost:5173", "X-Correlation-ID": "trace-error"},
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "private" not in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-correlation-id"] == "trace-error"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
