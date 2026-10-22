from pathlib import Path

import numpy as np

from worker.features.transaction_v1 import TransactionFeatureVector
from worker.processors.anomaly_processor import AnomalyProcessor


def features() -> TransactionFeatureVector:
    return TransactionFeatureVector(
        transaction_amount=5000,
        amount_difference_from_customer_average=4500,
        transactions_last_5_minutes=14,
        transactions_last_hour=50,
        decline_ratio=0.8,
        country_change=1,
        new_device_indicator=1,
        new_ip_address_indicator=1,
        unusual_transaction_time=1,
        payment_method_frequency=0.02,
        order_amount_deviation=4000,
    )


class FakeModel:
    def decision_function(self, values: np.ndarray) -> np.ndarray:
        assert values.shape == (1, 11)
        return np.asarray([-0.25])


class BrokenModel:
    def decision_function(self, values: np.ndarray) -> np.ndarray:
        raise RuntimeError("model execution failed")


def test_model_score_has_version_and_latency() -> None:
    result = AnomalyProcessor(FakeModel(), "model.v1").score(features())
    assert result.score == 0.25
    assert result.model_version == "model.v1"
    assert result.status == "scored"
    assert result.failure_reason is None
    assert result.latency_seconds >= 0


def test_model_failure_returns_persistable_fallback() -> None:
    result = AnomalyProcessor(BrokenModel(), "broken.v1").score(features())
    assert result.score == 0.0
    assert result.model_version == "fallback.v1"
    assert result.status == "fallback"
    assert result.failure_reason == "RuntimeError: model execution failed"


def test_missing_model_does_not_raise() -> None:
    processor = AnomalyProcessor.load(Path("missing.joblib"), Path("missing.json"))
    result = processor.score(features())
    assert result.status == "fallback"
    assert result.model_version == "fallback.v1"


def test_committed_model_loads_and_scores() -> None:
    root = Path(__file__).resolve().parents[4]
    processor = AnomalyProcessor.load(
        root / "model-artifacts" / "isolation_forest.v1.joblib",
        root / "model-artifacts" / "isolation_forest.v1.metadata.json",
    )
    result = processor.score(features())
    assert result.status == "scored"
    assert result.model_version == "isolation_forest.v1"
    assert np.isfinite(result.score)
