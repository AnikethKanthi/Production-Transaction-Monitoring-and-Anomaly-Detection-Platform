import hashlib
import json
import math
from pathlib import Path

import pytest

from worker.features.transaction_v1 import TransactionFeatureVector
from worker.processors.alert_processor import AlertPolicy, AlertSeverity
from worker.processors.anomaly_processor import AnomalyProcessor, ScoreResult


def features() -> TransactionFeatureVector:
    return TransactionFeatureVector(
        transaction_amount=5000,
        amount_difference_from_customer_average=4500,
        transactions_last_5_minutes=20,
        transactions_last_hour=60,
        decline_ratio=0.8,
        country_change=1,
        new_device_indicator=1,
        new_ip_address_indicator=1,
        unusual_transaction_time=1,
        payment_method_frequency=0.01,
        order_amount_deviation=4000,
    )


@pytest.mark.parametrize(
    "margin,severity",
    [
        (0, "low"),
        (0.024, "low"),
        (0.025, "medium"),
        (0.049, "medium"),
        (0.05, "high"),
        (0.099, "high"),
        (0.1, "critical"),
        (0.5, "critical"),
    ],
)
def test_each_severity_policy_and_inclusive_boundaries(margin, severity) -> None:
    policy = AlertPolicy("model.v1", 0.2)
    score = ScoreResult(0.2 + margin, "model.v1", "scored", None, 0.01)
    evidence = policy.evaluate(score, features())
    assert evidence is not None
    assert evidence["severity"] == severity
    assert evidence == policy.evaluate(score, features())
    assert evidence["reasons"] and "threshold" in evidence["reasons"][0]
    assert evidence["observed_features"]["transaction_amount"] == 5000
    assert set(AlertSeverity) == {"low", "medium", "high", "critical"}
    json.dumps(evidence, allow_nan=False)


@pytest.mark.parametrize(
    "value,version,status",
    [
        (math.nextafter(0.2, -math.inf), "model.v1", "scored"),
        (0.8, "model.v1", "fallback"),
        (0.8, "fallback.v1", "scored"),
        (0.8, "wrong.v1", "scored"),
        (float("nan"), "model.v1", "scored"),
        (float("inf"), "model.v1", "scored"),
    ],
)
def test_nonqualifying_scores_never_create_alerts(value, version, status) -> None:
    result = ScoreResult(value, version, status, None, 0.01)
    assert AlertPolicy("model.v1", 0.2).evaluate(result, features()) is None


def test_configuration_is_bound_to_exact_model(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[4] / "model-artifacts"
    policy = AlertPolicy.load(
        source / "isolation_forest.v1.threshold.json", source / "isolation_forest.v1.joblib"
    )
    assert policy is not None
    assert policy.model_version == "isolation_forest.v1"
    processor = AnomalyProcessor.load(
        source / "isolation_forest.v1.joblib", source / "isolation_forest.v1.metadata.json"
    )
    score = processor.score(features())
    assert score.status == "scored"
    assert policy.evaluate(score, features()) is not None
    model = tmp_path / "model.joblib"
    model.write_bytes(b"different-model")
    assert AlertPolicy.load(source / "isolation_forest.v1.threshold.json", model) is None
    assert AlertPolicy.load(tmp_path / "missing.json", model) is None


@pytest.mark.parametrize(
    "override",
    [
        {"comparator": ">"},
        {"configuration_version": "unknown"},
        {"feature_definition_version": "wrong"},
        {"threshold": float("inf")},
        {"segment_overrides": {"US": 0.4}},
    ],
)
def test_invalid_configuration_disables_alerts(tmp_path: Path, override) -> None:
    model = tmp_path / "model.joblib"
    model.write_bytes(b"model")
    config = {
        "model_version": "model.v1",
        "threshold": 0.2,
        "configuration_version": "anomaly_threshold.v1",
        "comparator": ">=",
        "segment_overrides": {},
        "feature_definition_version": "transaction_features.v1",
        "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
    } | override
    path = tmp_path / "threshold.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    assert AlertPolicy.load(path, model) is None
