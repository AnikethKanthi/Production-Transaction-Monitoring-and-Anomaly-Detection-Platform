"""Local components only: SQLite/ASGI API and the committed model, not a system SLA test."""

import argparse
import asyncio
import hashlib
import logging
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from performance_common import distribution, save_report
from seed_database import seed
from sqlalchemy import CheckConstraint, MetaData, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


async def benchmark(rows=2000, samples=200):
    from app.core.security import Principal, get_principal
    from app.db.base import Base
    from app.db.session import get_session
    from app.main import app
    from worker.events.transaction import TransactionData
    from worker.features.transaction_v1 import transform_transaction_features
    from worker.processors.anomaly_processor import AnomalyProcessor

    logging.getLogger().setLevel(logging.WARNING)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        clone = table.to_metadata(metadata)
        for constraint in list(clone.constraints):
            if isinstance(constraint, CheckConstraint) and "~" in str(
                constraint.sqltext
            ):
                clone.constraints.remove(constraint)
    metadata.create_all(engine)
    seed(engine, rows)
    factory = sessionmaker(engine)

    def session():
        with factory.begin() as value:
            yield value

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_principal] = lambda: Principal(
        username="component-benchmark", role="administrator"
    )
    latencies = []
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://component"
        ) as client:
            for index in range(samples + 10):
                before = time.perf_counter()
                response = await client.get(
                    "/transactions?status=completed&currency=USD&limit=20"
                )
                response.raise_for_status()
                if index >= 10:
                    latencies.append((time.perf_counter() - before) * 1000)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        engine.dispose()
    root = Path(__file__).resolve().parents[1]
    model_path = root / "model-artifacts/isolation_forest.v1.joblib"
    processor = AnomalyProcessor.load(
        model_path, root / "model-artifacts/isolation_forest.v1.metadata.json"
    )
    vector = transform_transaction_features(
        TransactionData(
            transaction_id="11111111-1111-4111-8111-111111111111",
            account_id="benchmark",
            amount="100",
            currency="USD",
            country="US",
            status="completed",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        [],
    )
    inference = []
    for index in range(samples + 10):
        result = processor.score(vector)
        if result.status != "scored":
            raise RuntimeError(
                "Component benchmark cannot measure fallback as model inference"
            )
        if index >= 10:
            inference.append(result.latency_seconds * 1000)
    return {
        "kind": "local_components_not_system_load",
        "recorded_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "rows": rows,
        "concurrency": 1,
        "warmup_samples": 10,
        "api_sqlite_asgi_ms": distribution(latencies),
        "model_inference_ms": distribution(inference),
        "model_version": result.model_version,
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "system_targets": {
            "api_p95": "not_assessed_without_network_postgres_redis",
            "alert_latency": "not_assessed_without_kafka_worker",
            "throughput_and_lag": "not_assessed_without_kafka_worker",
            "backup_restore": "not_executed_without_postgresql",
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=".local/component-performance.json")
    parser.add_argument("--samples", type=int, default=200)
    args = parser.parse_args()
    if not 20 <= args.samples <= 10000:
        parser.error("samples must be 20..10000")
    report = asyncio.run(benchmark(samples=args.samples))
    save_report(args.report, report)
    print(
        "Local component report saved; production performance targets are not assessed."
    )
