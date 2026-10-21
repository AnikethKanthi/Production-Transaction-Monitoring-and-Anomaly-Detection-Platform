from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

FEATURE_DEFINITION_VERSION = "transaction_features.v1"
FEATURE_NAMES = (
    "transaction_amount",
    "amount_difference_from_customer_average",
    "transactions_last_5_minutes",
    "transactions_last_hour",
    "decline_ratio",
    "country_change",
    "new_device_indicator",
    "new_ip_address_indicator",
    "unusual_transaction_time",
    "payment_method_frequency",
    "order_amount_deviation",
)


def feature_matrix(rows: Iterable[Mapping[str, object]]) -> NDArray[np.float64]:
    """Return finite model inputs in the canonical feature order."""
    matrix = np.asarray(
        [[_safe_number(row.get(name)) for name in FEATURE_NAMES] for row in rows],
        dtype=np.float64,
    )
    if matrix.ndim != 2 or matrix.shape[1] != len(FEATURE_NAMES):
        raise ValueError("feature data must contain at least one row")
    return matrix


def read_feature_csv(path: Path) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"training dataset is empty: {path}")
    return feature_matrix(rows), np.asarray([int(row["is_anomaly"]) for row in rows])


def _safe_number(value: object) -> float:
    if value in (None, ""):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid numeric feature value: {value!r}") from exc
    return number if np.isfinite(number) else 0.0
