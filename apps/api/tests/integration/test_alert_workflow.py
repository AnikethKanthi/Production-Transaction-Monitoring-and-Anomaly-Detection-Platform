import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from app.db.session import get_session
from app.main import app
from app.models import Alert, AlertAudit, Anomaly, Transaction

pytestmark = pytest.mark.integration


def test_postgres_investigation_and_version_conflict(migrated_connection):
    factory = sessionmaker(migrated_connection, expire_on_commit=False)
    alert_id, transaction_id, anomaly_id = uuid4(), uuid4(), uuid4()
    with factory.begin() as session:
        session.add(
            Transaction(
                id=transaction_id,
                account_id="acct-alert",
                amount=Decimal("500"),
                currency="USD",
                country="US",
                status="completed",
                occurred_at=datetime.now(UTC),
            )
        )
        session.flush()
        session.add(
            Anomaly(
                id=anomaly_id,
                transaction_id=transaction_id,
                score=0.4,
                model_version="test.v1",
                scoring_status="scored",
                inference_latency_seconds=0.01,
            )
        )
        session.flush()
        session.add(
            Alert(
                id=alert_id,
                transaction_id=transaction_id,
                anomaly_id=anomaly_id,
                event_id=uuid4(),
                severity="critical",
                policy_version="test.v1",
                model_version="test.v1",
                evidence={"reasons": ["High score"]},
            )
        )
        session.flush()
        session.add(
            AlertAudit(
                id=uuid4(),
                alert_id=alert_id,
                version=1,
                action="create",
                actor="system:test",
                reason="Test fixture",
                before=None,
                after={"status": "open", "assignee": None, "version": 1},
            )
        )

    def override_session():
        with factory.begin() as session:
            yield session

    async def workflow():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            path = f"/alerts/{alert_id}"
            body = {"expected_version": 1, "actor": "analyst", "reason": "Investigating"}
            acknowledged = await client.post(path + "/acknowledge", json=body)
            assert acknowledged.status_code == 200
            assert (await client.post(path + "/resolve", json=body)).status_code == 409
            assigned = await client.post(
                path + "/assign", json=body | {"expected_version": 2, "assignee": "agent-1"}
            )
            assert assigned.status_code == 200
            resolved = await client.post(path + "/resolve", json=body | {"expected_version": 3})
            assert resolved.status_code == 200
            assert resolved.json()["status"] == "resolved"
            history = (await client.get(path + "/audit")).json()
            assert [item["version"] for item in history] == [1, 2, 3, 4]

    app.dependency_overrides[get_session] = override_session
    try:
        asyncio.run(workflow())
    finally:
        app.dependency_overrides.clear()
