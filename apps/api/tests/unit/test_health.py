import asyncio

import httpx

from app.main import app


async def get(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


def test_health_contract() -> None:
    response = asyncio.run(get("/health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api", "version": "0.1.0"}


def test_health_is_documented() -> None:
    schema = asyncio.run(get("/openapi.json")).json()
    assert "/health" in schema["paths"]
