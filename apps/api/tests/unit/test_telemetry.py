import asyncio
import json
import logging

import httpx
from fastapi import FastAPI
from prometheus_client import generate_latest

from app.core.logging import JsonFormatter, request_id
from app.core.telemetry import LATENCY, REQUESTS, TelemetryMiddleware


def test_request_correlation_and_bounded_route_labels():
    application = FastAPI()
    application.add_middleware(TelemetryMiddleware)

    @application.get("/items/{item_id}")
    async def item(item_id: str):
        await asyncio.sleep(0)
        return {"correlation_id": request_id.get()}

    async def send():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as client:
            results = await asyncio.gather(
                *[
                    client.get(f"/items/{index}", headers={"X-Correlation-ID": f"request-{index}"})
                    for index in range(5)
                ]
            )
            for index, response in enumerate(results):
                assert response.headers["x-correlation-id"] == f"request-{index}"
                assert response.json()["correlation_id"] == f"request-{index}"
            invalid = await client.get("/items/unsafe", headers={"X-Correlation-ID": "bad value"})
            assert invalid.headers["x-correlation-id"] != "bad value"
            await client.get("/random-unknown-path-123")

    before = REQUESTS.labels("GET", "/items/{item_id}", "200")._value.get()
    asyncio.run(send())
    assert REQUESTS.labels("GET", "/items/{item_id}", "200")._value.get() == before + 6
    samples = generate_latest().decode()
    assert 'route="/items/{item_id}"' in samples
    assert 'route="unmatched"' in samples
    assert "random-unknown-path-123" not in samples
    assert request_id.get() is None


def test_unhandled_errors_count_as_500_and_restore_context():
    application = FastAPI()
    application.add_middleware(TelemetryMiddleware)

    @application.get("/fail")
    def fail():
        raise RuntimeError("deliberate test error")

    async def send():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            assert (await client.get("/fail")).status_code == 500

    before = REQUESTS.labels("GET", "/fail", "500")._value.get()
    asyncio.run(send())
    assert REQUESTS.labels("GET", "/fail", "500")._value.get() == before + 1
    assert LATENCY.labels("GET", "/fail")._sum.get() >= 0
    assert request_id.get() is None


def test_api_json_log_includes_correlation_transaction_and_exception():
    token = request_id.set("test-trace")
    try:
        record = logging.LogRecord(
            "test", logging.INFO, __file__, 1, "Transaction %s", ("saved",), None
        )
        record.transaction_id = "transaction-123"
        value = json.loads(JsonFormatter().format(record))
        assert value["correlation_id"] == "test-trace"
        assert value["transaction_id"] == "transaction-123"
        assert value["message"] == "Transaction saved"
    finally:
        request_id.reset(token)


def test_actual_api_prometheus_scrape_endpoint():
    from app.main import app

    async def send():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/health")
            response = await client.get("/metrics/prometheus")
            assert response.status_code == 200
            assert "text/plain" in response.headers["content-type"]
            assert "api_http_requests_total" in response.text
            assert "api_http_request_duration_seconds_bucket" in response.text

    asyncio.run(send())
