from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.ml.features import feature_matrix
from app.ml.registry import load_model


class AnomalyPredictor:
    def __init__(self, model_path: Path) -> None:
        self._model = load_model(model_path)

    def anomaly_score(self, features: Mapping[str, object]) -> float:
        """Return a score where larger values mean more anomalous."""
        return float(-self._model.decision_function(feature_matrix([features]))[0])
