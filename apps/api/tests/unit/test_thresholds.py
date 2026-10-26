import hashlib
import shutil
from pathlib import Path

import numpy as np
import pytest

from app.ml.thresholds import (
    MAX_ALERT_RATE,
    classification_metrics,
    evaluation_data,
    run_evaluation,
    select_threshold,
)


def test_confusion_matrix_and_inclusive_boundary() -> None:
    result = classification_metrics([1, 1, 0, 0], [0.7, 0.2, 0.5, 0.1], 0.5)
    assert result["true_positives"] == result["false_positives"] == 1
    assert result["true_negatives"] == result["false_negatives"] == 1
    assert result["precision"] == result["recall"] == result["f1"] == 0.5
    assert result["alerts_per_10000_transactions"] == 5000


def test_selection_respects_volume_with_tied_scores() -> None:
    labels = np.asarray([0] * 18 + [1, 1])
    scores = np.asarray([0.0] * 18 + [0.8, 0.9])
    threshold, sweep = select_threshold(labels, scores)
    assert threshold == 0.8
    assert classification_metrics(labels, scores, threshold)["alert_rate"] <= MAX_ALERT_RATE
    assert len(sweep) == 4


@pytest.mark.parametrize("labels,scores", [([], []), ([2], [0.1]), ([1], [float("nan")])])
def test_invalid_scores_and_labels_are_rejected(labels, scores) -> None:
    with pytest.raises(ValueError):
        classification_metrics(labels, scores, 0.0)


def test_labeled_evaluation_data_is_reproducible_and_separate() -> None:
    first = evaluation_data()
    assert first == evaluation_data()
    assert len({row["transaction_id"] for row in first}) == len(first)
    assert all(row["occurred_at"].startswith("2025-02-") for row in first)
    assert sum(row["is_anomaly"] for row in first) == 240
    assert any(row["scenario"] == "subtle_account_takeover" for row in first)


def test_evaluation_outputs_repeat_and_do_not_modify_model(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[4] / "model-artifacts"
    artifacts = tmp_path / "model-artifacts"
    artifacts.mkdir()
    for suffix in ("joblib", "metadata.json"):
        shutil.copy2(source / f"isolation_forest.v1.{suffix}", artifacts)
    model_path = artifacts / "isolation_forest.v1.joblib"
    before = hashlib.sha256(model_path.read_bytes()).hexdigest()
    first = run_evaluation(tmp_path)
    config_path = artifacts / "isolation_forest.v1.threshold.json"
    config_bytes = config_path.read_bytes()
    second = run_evaluation(tmp_path)
    assert first == second
    assert config_bytes == config_path.read_bytes()
    assert first["configuration"]["model_sha256"] == before
    assert hashlib.sha256(model_path.read_bytes()).hexdigest() == before
    assert first["calibration"]["rows"] == first["holdout"]["rows"] == 1200
    assert first["calibration"]["alert_rate"] <= MAX_ALERT_RATE
    assert first["holdout"]["true_positives"] + first["holdout"]["false_negatives"] == 120
    assert set(first["segments"]) == {"country", "payment_method"}
