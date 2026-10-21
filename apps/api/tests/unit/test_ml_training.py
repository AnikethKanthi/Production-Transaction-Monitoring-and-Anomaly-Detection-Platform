from pathlib import Path

import joblib
import numpy as np

from app.ml.features import FEATURE_NAMES, feature_matrix
from app.ml.train import RANDOM_SEED, generate_synthetic_dataset, train


def test_synthetic_dataset_is_deterministic() -> None:
    assert generate_synthetic_dataset(20, 5) == generate_synthetic_dataset(20, 5)
    assert RANDOM_SEED == 42


def test_missing_and_non_finite_features_are_safe() -> None:
    matrix = feature_matrix([{"transaction_amount": None, "decline_ratio": float("nan")}])
    assert matrix.shape == (1, len(FEATURE_NAMES))
    assert np.isfinite(matrix).all()
    assert not matrix.any()


def test_training_produces_versioned_artifacts_and_separates_anomalies(
    tmp_path: Path,
) -> None:
    result = train(tmp_path)
    model_path = Path(result["model"])
    metadata_path = Path(result["metadata"])
    assert model_path.name == "isolation_forest.v1.joblib"
    assert model_path.exists() and metadata_path.exists()
    assert (tmp_path / "model-artifacts" / "isolation_forest.v1.scores.svg").exists()
    assert result["anomaly_mean_anomaly_score"] > result["normal_mean_anomaly_score"]
    assert result["anomaly_score_separation_rate"] > 0.9
    assert hasattr(joblib.load(model_path), "decision_function")
