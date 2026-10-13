import asyncio
from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import Connection
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_session
from app.main import app

pytestmark = pytest.mark.integration


class ApiClient:
    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self.request("POST", path, **kwargs)


@pytest.fixture
def client(migrated_connection: Connection) -> Iterator[ApiClient]:
    factory = sessionmaker(migrated_connection, expire_on_commit=False)

    def override_session() -> Iterator[Session]:
        with factory.begin() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        yield ApiClient()
    finally:
        app.dependency_overrides.clear()


def payload(**overrides) -> dict:
    values = {
        "account_id": "acct-1",
        "merchant_id": "merchant-1",
        "amount": "125.50",
        "currency": "USD",
        "country": "US",
        "status": "pending",
        "occurred_at": "2026-10-13T14:30:00Z",
    }
    return values | overrides


def test_create_and_get_transaction(client: ApiClient) -> None:
    created = client.post("/transactions", json=payload())
    assert created.status_code == 201
    body = created.json()
    assert body["amount"] == "125.50"
    assert body["country"] == "US"
    assert body["status"] == "pending"
    assert body["created_at"].endswith("Z")

    fetched = client.get(f"/transactions/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body


def test_list_filters_and_pagination(client: ApiClient) -> None:
    rows = [
        payload(
            amount="10.00",
            country="US",
            currency="USD",
            status="pending",
            occurred_at="2026-10-10T10:00:00Z",
        ),
        payload(
            amount="20.00",
            country="GB",
            currency="GBP",
            status="completed",
            occurred_at="2026-10-11T10:00:00Z",
        ),
        payload(
            amount="30.00",
            country="US",
            currency="USD",
            status="completed",
            occurred_at="2026-10-12T10:00:00Z",
        ),
    ]
    for row in rows:
        assert client.post("/transactions", json=row).status_code == 201

    response = client.get(
        "/transactions",
        params={
            "status": "completed",
            "country": "US",
            "currency": "USD",
            "min_amount": "25.00",
            "max_amount": "35.00",
            "occurred_from": "2026-10-12T00:00:00Z",
            "occurred_to": "2026-10-12T23:59:59Z",
        },
    )
    assert response.status_code == 200
    assert [item["amount"] for item in response.json()["items"]] == ["30.00"]
    assert response.json()["pagination"] == {"limit": 50, "offset": 0, "total": 1}

    page = client.get("/transactions", params={"limit": 1, "offset": 1})
    assert page.status_code == 200
    assert page.json()["pagination"] == {"limit": 1, "offset": 1, "total": 3}
    assert page.json()["items"][0]["amount"] == "20.00"


@pytest.mark.parametrize(
    ("bad_payload", "location"),
    [
        (payload(amount="0"), ["body", "amount"]),
        (payload(currency="usd"), ["body", "currency"]),
        (payload(country="USA"), ["body", "country"]),
        (payload(status="approved"), ["body", "status"]),
        (payload(occurred_at="2026-10-13T14:30:00"), ["body"]),
    ],
)
def test_invalid_create_returns_structured_error(
    client: ApiClient, bad_payload: dict, location: list[str]
) -> None:
    response = client.post("/transactions", json=bad_payload)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert any(detail["loc"][: len(location)] == location for detail in error["details"])


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"offset": -1},
        {"min_amount": "20", "max_amount": "10"},
        {"occurred_from": "2026-10-14T00:00:00Z", "occurred_to": "2026-10-13T00:00:00Z"},
        {"occurred_from": "2026-10-13T00:00:00"},
        {"unknown": "value"},
    ],
)
def test_invalid_filters_return_structured_error(client: ApiClient, params: dict) -> None:
    response = client.get("/transactions", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_missing_and_malformed_ids(client: ApiClient) -> None:
    missing_id = uuid4()
    response = client.get(f"/transactions/{missing_id}")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "transaction_not_found",
            "message": f"Transaction {missing_id} was not found",
        }
    }
    malformed = client.get("/transactions/not-a-uuid")
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "validation_error"


def test_openapi_documents_examples_filters_and_errors(client: ApiClient) -> None:
    schema = client.get("/openapi.json").json()
    create = schema["paths"]["/transactions"]["post"]
    create_schema = schema["components"]["schemas"]["TransactionCreate"]
    assert create_schema["examples"][0]["country"] == "US"
    assert set(create["responses"]) >= {"201", "422"}
    parameters = {item["name"] for item in schema["paths"]["/transactions"]["get"]["parameters"]}
    assert parameters >= {
        "status",
        "country",
        "currency",
        "min_amount",
        "max_amount",
        "occurred_from",
        "occurred_to",
        "limit",
        "offset",
    }
    details = schema["paths"]["/transactions/{transaction_id}"]["get"]
    assert set(details["responses"]) >= {"200", "404", "422"}
