from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import joblib
import numpy as np
from sqlalchemy.orm import Session

from worker.features.transaction_v1 import FEATURE_DEFINITION_VERSION, TransactionFeatureVector
from worker.monitoring.metrics import INFERENCE_LATENCY, INFERENCE_RESULTS
from worker.persistence.models import AnomalyRecord

logger = logging.getLogger(__name__)
FALLBACK_MODEL_VERSION = "fallback.v1"


@dataclass(frozen=True)
class ScoreResult:
    score: float
    model_version: str
    status: str
    failure_reason: str | None
    latency_seconds: float


class AnomalyProcessor:
    def __init__(
        self,
        model: Any | None,
        model_version: str = FALLBACK_MODEL_VERSION,
        load_error: str | None = None,
    ) -> None:
        self.model = model
        self.model_version = model_version
        self.load_error = load_error

    @classmethod
    def load(cls, model_path: Path, metadata_path: Path) -> "AnomalyProcessor":
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata["feature_definition_version"] != FEATURE_DEFINITION_VERSION:
                raise ValueError("model feature definition is incompatible with the worker")
            expected_names = list(TransactionFeatureVector.model_fields)
            if metadata["feature_names"] != expected_names:
                raise ValueError("model feature order is incompatible with the worker")
            model = joblib.load(model_path)
            version = str(metadata["model_version"])
        except Exception as error:
            reason = _failure_reason(error)
            logger.error("Anomaly model unavailable; fallback scoring enabled: %s", reason)
            return cls(None, load_error=reason)
        logger.info("Loaded anomaly model version=%s path=%s", version, model_path)
        return cls(model, model_version=version)

    def score(self, features: TransactionFeatureVector) -> ScoreResult:
        started = time.perf_counter()
        status = "scored"
        reason = None
        model_version = self.model_version
        try:
            if self.model is None:
                raise RuntimeError(self.load_error or "model unavailable")
            vector = np.asarray(
                [[getattr(features, name) for name in TransactionFeatureVector.model_fields]]
            )
            score = float(-self.model.decision_function(vector)[0])
            if not math.isfinite(score):
                raise ValueError("model returned a non-finite score")
        except Exception as error:
            score = 0.0
            status = "fallback"
            model_version = FALLBACK_MODEL_VERSION
            reason = _failure_reason(error)
            logger.warning("Anomaly scoring failed; stored fallback score: %s", reason)
        latency = time.perf_counter() - started
        INFERENCE_LATENCY.labels(model_version=model_version, status=status).observe(latency)
        INFERENCE_RESULTS.labels(model_version=model_version, status=status).inc()
        return ScoreResult(score, model_version, status, reason, latency)

    def store(self, session: Session, transaction_id, result: ScoreResult) -> AnomalyRecord:
        record = AnomalyRecord(
            id=uuid4(),
            transaction_id=transaction_id,
            score=result.score,
            model_version=result.model_version,
            scoring_status=result.status,
            failure_reason=result.failure_reason,
            inference_latency_seconds=result.latency_seconds,
        )
        session.add(record)
        return record


def _failure_reason(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"[:512]
