import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import CheckConstraint, MetaData, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.repositories.transactions import TransactionRepository
from app.db.session import get_session
from app.main import app
from app.models import Alert, Anomaly, Transaction


@pytest.fixture
def factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        clone = table.to_metadata(metadata)
        for constraint in list(clone.constraints):
            if isinstance(constraint, CheckConstraint) and "~" in str(constraint.sqltext):
                clone.constraints.remove(constraint)
    metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as session:
        for index, amount in enumerate([30, 10, 10, 50]):
            session.add(
                Transaction(
                    id=UUID(int=index + 1),
                    account_id="acct_%" if index == 0 else "acct-test",
                    merchant_id="merchant-special" if index == 3 else "shop",
                    amount=Decimal(amount),
                    currency="USD",
                    country="US",
                    status="completed",
                    occurred_at=datetime.now(UTC),
                )
            )
    yield factory
    engine.dispose()


def test_search_sort_and_pagination_are_database_backed(factory):
    with factory() as session:
        repository = TransactionRepository(session)
        rows, total = repository.list(
            search="ACCT", sort_by="amount", sort_order="asc", limit=2, offset=1
        )
        assert total == 4
        assert [item.id for item in rows] == [UUID(int=3), UUID(int=1)]
        assert repository.list(search="_%")[1] == 1
        assert repository.list(search="merchant-special")[1] == 1
        assert repository.list(search=str(UUID(int=2)))[1] == 1
        assert repository.list(search="no match")[1] == 0
        with pytest.raises(ValueError):
            repository.list(sort_by="amount; drop table transactions")


def test_investigation_api_links_transaction_score_and_alert(factory):
    anomaly_id, alert_id = uuid4(), uuid4()
    with factory.begin() as session:
        session.add(
            Anomaly(
                id=anomaly_id,
                transaction_id=UUID(int=1),
                score=0.4,
                model_version="fixture.v1",
                scoring_status="scored",
                inference_latency_seconds=0.01,
            )
        )
        session.flush()
        session.add(
            Alert(
                id=alert_id,
                transaction_id=UUID(int=1),
                anomaly_id=anomaly_id,
                event_id=uuid4(),
                severity="high",
                policy_version="fixture.v1",
                model_version="fixture.v1",
                evidence={"score": 0.4, "reasons": ["Suspicious amount"]},
            )
        )

    def override():
        with factory.begin() as session:
            yield session

    async def send():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(f"/transactions/{UUID(int=1)}/investigation")
            assert response.status_code == 200
            data = response.json()
            assert data["transaction"]["id"] == str(UUID(int=1))
            assert data["anomaly"]["score"] == 0.4
            assert data["alerts"][0]["id"] == str(alert_id)
            unscored = await client.get(f"/transactions/{UUID(int=2)}/investigation")
            assert unscored.json()["anomaly"] is None
            assert unscored.json()["alerts"] == []
            assert (await client.get(f"/transactions/{uuid4()}/investigation")).status_code == 404
            assert (await client.get("/transactions?sort_by=invalid")).status_code == 422
            filtered = await client.get(
                "/transactions?search=merchant-special&sort_by=amount&sort_order=asc"
            )
            assert filtered.status_code == 200
            assert filtered.json()["pagination"]["total"] == 1
            assert (await client.get(f"/alerts?transaction_id={UUID(int=1)}")).json()["pagination"][
                "total"
            ] == 1
            assert (await client.get(f"/alerts?transaction_id={UUID(int=2)}")).json()["items"] == []

    app.dependency_overrides[get_session] = override
    try:
        asyncio.run(send())
    finally:
        app.dependency_overrides.clear()
