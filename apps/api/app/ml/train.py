from __future__ import annotations

import csv
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.ml.evaluate import evaluate_scores
from app.ml.features import FEATURE_DEFINITION_VERSION, FEATURE_NAMES, read_feature_csv
from app.ml.registry import save_model

MODEL_VERSION = "isolation_forest.v1"
RANDOM_SEED = 42
DATA_START = datetime(2025, 1, 1, tzinfo=UTC)


def generate_synthetic_dataset(
    normal_count: int = 2000, anomaly_count: int = 200, seed: int = RANDOM_SEED
) -> list[dict[str, Any]]:
    """Generate deterministic model-ready transactions with intentionally distinct anomalies."""
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for index in range(normal_count + anomaly_count):
        anomalous = index >= normal_count
        if anomalous:
            amount = rng.lognormal(mean=7.2, sigma=0.6)
            avg_difference = amount * rng.uniform(0.55, 0.95)
            five_minutes = int(rng.integers(8, 25))
            one_hour = int(five_minutes + rng.integers(18, 70))
            decline_ratio = rng.uniform(0.55, 1.0)
            binary = rng.binomial(1, 0.82, size=4)
            payment_frequency = rng.uniform(0.0, 0.12)
            order_deviation = amount * rng.uniform(0.45, 0.9)
        else:
            amount = rng.lognormal(mean=4.6, sigma=0.35)
            avg_difference = rng.normal(0, 18)
            five_minutes = int(rng.poisson(0.8) + 1)
            one_hour = int(five_minutes + rng.poisson(5))
            decline_ratio = rng.beta(1.2, 14)
            binary = rng.binomial(1, 0.04, size=4)
            payment_frequency = rng.beta(4, 3)
            order_deviation = rng.normal(0, 14)
        occurred_at = DATA_START + timedelta(minutes=5 * index)
        rows.append(
            {
                "transaction_id": f"synthetic-{index:06d}",
                "occurred_at": occurred_at.isoformat().replace("+00:00", "Z"),
                "transaction_amount": round(float(amount), 6),
                "amount_difference_from_customer_average": round(float(avg_difference), 6),
                "transactions_last_5_minutes": five_minutes,
                "transactions_last_hour": one_hour,
                "decline_ratio": round(float(decline_ratio), 6),
                "country_change": int(binary[0]),
                "new_device_indicator": int(binary[1]),
                "new_ip_address_indicator": int(binary[2]),
                "unusual_transaction_time": int(binary[3]),
                "payment_method_frequency": round(float(payment_frequency), 6),
                "order_amount_deviation": round(float(order_deviation), 6),
                "is_anomaly": int(anomalous),
            }
        )
    return rows


def write_dataset(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def train(output_root: Path) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    timer = time.perf_counter()
    raw_path = output_root / "data" / "synthetic" / f"{MODEL_VERSION}.csv"
    processed_path = output_root / "data" / "processed" / f"{MODEL_VERSION}.features.csv"
    rows = generate_synthetic_dataset()
    write_dataset(rows, raw_path)
    write_dataset(rows, processed_path)
    features, labels = read_feature_csv(processed_path)
    model = Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "isolation_forest",
                IsolationForest(
                    n_estimators=250,
                    contamination=float(labels.mean()),
                    max_samples="auto",
                    random_state=RANDOM_SEED,
                    n_jobs=1,
                ),
            ),
        ]
    )
    model.fit(features[labels == 0])
    scores = -model.decision_function(features)
    evaluation = evaluate_scores(labels, scores, output_root / "model-artifacts", MODEL_VERSION)
    finished_at = datetime.now(UTC)
    metadata: dict[str, Any] = {
        "model_version": MODEL_VERSION,
        "model_type": "sklearn.ensemble.IsolationForest",
        "feature_definition_version": FEATURE_DEFINITION_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "random_seed": RANDOM_SEED,
        "parameters": model.named_steps["isolation_forest"].get_params(),
        "training": {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": round(time.perf_counter() - timer, 6),
            "normal_rows": int((labels == 0).sum()),
            "anomaly_rows": int((labels == 1).sum()),
            "fit_rows": int((labels == 0).sum()),
            "data_start": rows[0]["occurred_at"],
            "data_end": rows[-1]["occurred_at"],
            "dataset_sha256": hashlib.sha256(processed_path.read_bytes()).hexdigest(),
        },
        "evaluation": evaluation,
        "library_versions": _library_versions(),
    }
    model_path, metadata_path = save_model(model, metadata, output_root / "model-artifacts")
    return {"model": str(model_path), "metadata": str(metadata_path), **evaluation}


def _library_versions() -> dict[str, str]:
    import joblib
    import sklearn

    return {
        "joblib": joblib.__version__,
        "numpy": np.__version__,
        "scikit_learn": sklearn.__version__,
    }


def print_result(result: dict[str, Any]) -> None:
    print(json.dumps(result, indent=2, sort_keys=True))
