"""Guards the deterministic fixture used by the live Compose workflow."""

# ruff: noqa: E402

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from scripts.run_end_to_end import HISTORY_COUNT, anomaly_sequence  # noqa: E402

from worker.features.transaction_v1 import HistoricalTransaction, transform_transaction_features
from worker.processors.alert_processor import AlertPolicy
from worker.processors.anomaly_processor import AnomalyProcessor


def test_end_to_end_fixture_triggers_committed_alert_policy() -> None:
    events = anomaly_sequence(datetime(2026, 11, 9, 1, 30, tzinfo=UTC))
    target = events[-1]
    history = [
        HistoricalTransaction(
            transaction_id=event.data.transaction_id,
            amount=event.data.amount,
            currency=event.data.currency,
            country=event.data.country,
            status=event.data.status,
            occurred_at=event.data.occurred_at,
            device_id=event.data.device_id,
            ip_address=event.data.ip_address,
            payment_method=event.data.payment_method,
            order_amount=event.data.order_amount,
        )
        for event in events[:-1]
    ]
    features = transform_transaction_features(target.data, history)
    model_path = ROOT / "model-artifacts" / "isolation_forest.v1.joblib"
    metadata_path = ROOT / "model-artifacts" / "isolation_forest.v1.metadata.json"
    threshold_path = ROOT / "model-artifacts" / "isolation_forest.v1.threshold.json"
    processor = AnomalyProcessor.load(model_path, metadata_path)
    policy = AlertPolicy.load(threshold_path, model_path)

    score = processor.score(features)
    evidence = policy.evaluate(score, features) if policy else None

    assert len(events) == HISTORY_COUNT + 1
    assert len({event.event_id for event in events}) == len(events)
    assert features.transactions_last_5_minutes >= 4
    assert features.decline_ratio == 1.0
    assert features.country_change == 1
    assert evidence is not None
    assert evidence["model_version"] == "isolation_forest.v1"
