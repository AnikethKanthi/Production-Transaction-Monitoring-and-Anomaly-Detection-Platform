import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.repositories.alerts import AlertRepository
from app.db.session import get_session
from app.main import app
from app.models import Alert, AlertAudit
from app.schemas.alert import AlertMutation
from app.services.alert_service import AlertService, AlertWorkflowError


class Client:
    def request(self, method, path, **kwargs):
        async def send():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())


@pytest.fixture
def workflow():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    # Minimal parent tables isolate workflow SQL from PostgreSQL-specific transaction checks.
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE transactions (id CHAR(32) PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE anomalies (id CHAR(32) PRIMARY KEY)")
    Alert.__table__.create(engine)
    AlertAudit.__table__.create(engine)
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    with factory.begin() as session:
        transaction_id, anomaly_id, alert_id = uuid4(), uuid4(), uuid4()
        session.connection().exec_driver_sql(
            "INSERT INTO transactions VALUES (?)", (transaction_id.hex,)
        )
        session.connection().exec_driver_sql("INSERT INTO anomalies VALUES (?)", (anomaly_id.hex,))
        session.add(
            Alert(
                id=alert_id,
                transaction_id=transaction_id,
                anomaly_id=anomaly_id,
                event_id=uuid4(),
                severity="high",
                policy_version="test.v1",
                model_version="test.v1",
                evidence={"reasons": ["Suspicious transaction"]},
                created_at=datetime.now(UTC),
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
                reason="Fixture created",
                before=None,
                after={"status": "open", "assignee": None, "version": 1},
            )
        )

    def session_override():
        with factory.begin() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    try:
        yield Client(), factory, f"/alerts/{alert_id}"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def payload(version=1, **kwargs):
    return {
        "expected_version": version,
        "actor": "analyst-17",
        "reason": "Reviewed transaction evidence",
        **kwargs,
    }


def test_complete_acknowledge_assign_reassign_resolve_workflow(workflow):
    client, _, path = workflow
    assert client.request("GET", path).json()["status"] == "open"
    acknowledged = client.request("POST", path + "/acknowledge", json=payload())
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "acknowledged"
    assert acknowledged.json()["version"] == 2
    assigned = client.request("POST", path + "/assign", json=payload(2, assignee="agent-1"))
    assert assigned.status_code == 200
    assert assigned.json()["status"] == "acknowledged"
    reassigned = client.request("POST", path + "/assign", json=payload(3, assignee="agent-2"))
    assert reassigned.status_code == 200
    resolved = client.request("POST", path + "/resolve", json=payload(4))
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    history = client.request("GET", path + "/audit").json()
    assert [item["version"] for item in history] == [1, 2, 3, 4, 5]
    assert [item["action"] for item in history] == [
        "create",
        "acknowledge",
        "assign",
        "assign",
        "resolve",
    ]
    assert all(item["actor"] == "analyst-17" for item in history[1:])
    assert history[3]["before"]["assignee"] == "agent-1"
    assert history[3]["after"]["assignee"] == "agent-2"
    assert client.request("GET", path).json()["audit_history"] == history


def test_false_positive_closes_alert_and_is_auditable(workflow):
    client, _, path = workflow
    response = client.request("POST", path + "/false-positive", json=payload())
    assert response.status_code == 200
    assert response.json()["status"] == "false_positive"
    audit = client.request("GET", path + "/audit").json()[-1]
    assert audit["before"]["status"] == "open"
    assert audit["after"]["status"] == "false_positive"
    assert audit["reason"] == payload()["reason"]


def test_list_filters_and_pagination(workflow):
    client, _, path = workflow
    response = client.request(
        "GET", "/alerts", params={"status": "open", "severity": "high", "limit": 1}
    )
    assert response.status_code == 200
    assert response.json()["pagination"] == {"limit": 1, "offset": 0, "total": 1}
    assert len(response.json()["items"]) == 1
    assert client.request("GET", "/alerts", params={"severity": "low"}).json()["items"] == []
    assert client.request("GET", "/alerts", params={"offset": 1}).json()["items"] == []
    client.request("POST", path + "/resolve", json=payload())
    assert client.request("GET", "/alerts", params={"status": "open"}).json()["items"] == []
    assert len(client.request("GET", "/alerts", params={"status": "resolved"}).json()["items"]) == 1


@pytest.mark.parametrize("action", ["acknowledge", "assign", "resolve", "false-positive"])
def test_stale_version_returns_409_without_audit_entry(workflow, action):
    client, _, path = workflow
    client.request("POST", path + "/acknowledge", json=payload())
    body = payload(1, **({"assignee": "agent"} if action == "assign" else {}))
    response = client.request("POST", path + "/" + action, json=body)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "alert_version_conflict"
    assert len(client.request("GET", path + "/audit").json()) == 2


@pytest.mark.parametrize("closed_action", ["resolve", "false-positive"])
@pytest.mark.parametrize("action", ["acknowledge", "assign", "resolve", "false-positive"])
def test_terminal_alerts_reject_all_mutations(workflow, closed_action, action):
    client, _, path = workflow
    client.request("POST", path + "/" + closed_action, json=payload())
    body = payload(2, **({"assignee": "agent"} if action == "assign" else {}))
    assert client.request("POST", path + "/" + action, json=body).status_code == 409
    assert len(client.request("GET", path + "/audit").json()) == 2


@pytest.mark.parametrize(
    "body",
    [
        {},
        payload(0),
        payload(True),
        payload("1"),
        payload(actor=" "),
        payload(reason=" "),
        payload(unexpected="field"),
    ],
)
def test_invalid_mutations_return_422(workflow, body):
    client, _, path = workflow
    assert client.request("POST", path + "/acknowledge", json=body).status_code == 422


def test_missing_alert_and_invalid_filters(workflow):
    client, _, _ = workflow
    path = f"/alerts/{uuid4()}"
    assert client.request("GET", path).status_code == 404
    assert client.request("GET", path + "/audit").status_code == 404
    assert client.request("POST", path + "/resolve", json=payload()).status_code == 404
    for params in ({"status": "bad"}, {"severity": "bad"}, {"limit": 101}, {"offset": -1}):
        assert client.request("GET", "/alerts", params=params).status_code == 422


def test_compare_and_swap_rejects_a_session_with_stale_loaded_state(workflow):
    _, factory, path = workflow
    from uuid import UUID

    alert_id = UUID(path.split("/")[-1])
    with factory() as stale:
        original = stale.get(Alert, alert_id)
        assert original.version == 1
        with factory.begin() as fresh:
            AlertService(AlertRepository(fresh)).mutate(
                alert_id, "acknowledge", AlertMutation(**payload())
            )
        with pytest.raises(AlertWorkflowError) as error:
            AlertService(AlertRepository(stale)).mutate(
                alert_id, "resolve", AlertMutation(**payload())
            )
        assert error.value.code == "alert_version_conflict"
        stale.rollback()


def test_audit_failure_rolls_back_state_and_version(workflow):
    client, factory, path = workflow

    def reject_audit(mapper, connection, target):
        raise RuntimeError("audit unavailable")

    event.listen(AlertAudit, "before_insert", reject_audit)
    try:
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.request("POST", path + "/acknowledge", json=payload())
    finally:
        event.remove(AlertAudit, "before_insert", reject_audit)
    response = client.request("GET", path).json()
    assert response["status"] == "open" and response["version"] == 1
    with factory() as session:
        assert len(list(session.scalars(select(AlertAudit)))) == 1
