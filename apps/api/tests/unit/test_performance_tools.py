import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy import CheckConstraint, MetaData, create_engine, func, select

from app.models import Transaction

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from performance_common import distribution  # noqa: E402
from run_load_test import api_load  # noqa: E402
from run_recovery_drill import Drill  # noqa: E402
from seed_database import seed  # noqa: E402


def test_percentiles_and_empty_samples():
    assert distribution([])["p95"] is None
    assert distribution(range(1, 101))["p95"] == 95
    assert distribution([3])["p95"] == 3


def test_batch_seed_is_idempotent_and_respects_known_fixture():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    table = Transaction.__table__.to_metadata(metadata)
    for constraint in list(table.constraints):
        if isinstance(constraint, CheckConstraint) and "~" in str(constraint.sqltext):
            table.constraints.remove(constraint)
    metadata.create_all(engine)
    seed(engine, 31, batch_size=7)
    seed(engine, 31, batch_size=10)
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(table)) == 31
        assert (
            connection.scalar(
                select(func.count()).select_from(table).where(table.c.status == "failed")
            )
            == 4
        )
    engine.dispose()


def test_http_load_counts_errors_and_does_not_claim_a_pass(monkeypatch):
    original = httpx.AsyncClient

    async def handler(request):
        assert request.headers["authorization"] == "Bearer private-token"
        return httpx.Response(429)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)),
    )
    report = asyncio.run(api_load("http://test", "private-token", 5, 2, 1000))
    assert report["requests"] == 5
    assert report["statuses"] == {"429": 5}
    assert report["api_p95_under_300ms"] is False
    assert "private-token" not in str(report)


def test_drill_rejects_shared_project_and_restarts_services_on_restore_failure(tmp_path):
    with pytest.raises(ValueError):
        Drill("production")
    drill = Drill("drill-unit")
    drill.service = Mock()
    drill.fingerprint = Mock(return_value={"transactions": "1|hash"})
    drill.command = Mock(return_value=b"transactions\n")
    calls = []

    def pg(tool, *args, **kwargs):
        calls.append((tool, args))
        if tool == "pg_dump":
            kwargs["stdout"].write(b"custom-archive")
        if tool == "pg_restore":
            raise RuntimeError("simulated restore failure")
        return b""

    drill.pg = pg
    with pytest.raises(RuntimeError):
        drill.backup_restore(tmp_path)
    target = next(args[0] for tool, args in calls if tool == "createdb")
    assert target.startswith("recovery_")
    assert ("dropdb", (target,)) in calls
    assert ("dropdb", ("transactions",)) not in calls
    assert drill.service.call_args_list[-2].args == ("start", "api")
    assert drill.service.call_args_list[-1].args == ("start", "worker")


def test_backup_restore_verifies_rows_and_indexes(tmp_path):
    drill = Drill("drill-unit")
    drill.service = Mock()
    drill.command = Mock(return_value=b"transactions\n")
    drill.fingerprint = Mock(return_value={"transactions": "3|digest", "indexes": "indexdef"})

    def pg(tool, *args, **kwargs):
        if tool == "pg_dump":
            kwargs["stdout"].write(b"custom-archive")
        if tool == "pg_restore":
            assert kwargs["stdin"].read() == b"custom-archive"
        return b""

    drill.pg = pg
    report = drill.backup_restore(tmp_path)
    assert report["verified"] is True
    assert report["archive_bytes"] == len(b"custom-archive")
    assert drill.fingerprint.call_count == 3
