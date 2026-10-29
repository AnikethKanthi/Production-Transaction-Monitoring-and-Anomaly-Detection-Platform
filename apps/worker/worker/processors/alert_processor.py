"""Versioned, deterministic alert decisions and database-enforced deduplication."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from worker.events.transaction import TransactionEvent
from worker.features.transaction_v1 import FEATURE_DEFINITION_VERSION, TransactionFeatureVector
from worker.persistence.models import AlertAuditRecord, AlertRecord
from worker.processors.anomaly_processor import ScoreResult

logger = logging.getLogger(__name__)
POLICY_VERSION = "anomaly_alert.v1"


class AlertSeverity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


@dataclass(frozen=True)
class AlertPolicy:
    model_version: str
    threshold: float
    threshold_configuration_version: str = "anomaly_threshold.v1"

    def __post_init__(self) -> None:
        if not self.model_version or not math.isfinite(self.threshold):
            raise ValueError("alert policy requires a model version and finite threshold")

    @classmethod
    def load(cls, threshold_path: Path, model_path: Path) -> AlertPolicy | None:
        """Disable model alerts if the threshold sidecar cannot be verified."""
        try:
            config = json.loads(threshold_path.read_text(encoding="utf-8"))
            if config["configuration_version"] != "anomaly_threshold.v1":
                raise ValueError("unsupported threshold configuration")
            if config["comparator"] != ">=" or config["segment_overrides"]:
                raise ValueError("alert policy requires an inclusive global threshold")
            if config["feature_definition_version"] != FEATURE_DEFINITION_VERSION:
                raise ValueError("threshold feature definition mismatch")
            if config["model_sha256"] != hashlib.sha256(model_path.read_bytes()).hexdigest():
                raise ValueError("threshold model hash mismatch")
            return cls(config["model_version"], float(config["threshold"]))
        except (OSError, ValueError, KeyError, TypeError) as error:
            logger.error("Model alerts disabled: threshold configuration unavailable: %s", error)
            return None

    def evaluate(self, score: ScoreResult, features: TransactionFeatureVector) -> dict | None:
        if (
            score.status != "scored"
            or score.model_version == "fallback.v1"
            or score.model_version != self.model_version
            or not math.isfinite(score.score)
            or score.score < self.threshold
        ):
            return None
        # Compare against absolute cutoffs to make boundary behavior explicit.
        severity = AlertSeverity.low
        lower_bound = self.threshold
        upper_bound = self.threshold + 0.025
        for level, margin, next_margin in (
            (AlertSeverity.medium, 0.025, 0.05),
            (AlertSeverity.high, 0.05, 0.1),
            (AlertSeverity.critical, 0.1, None),
        ):
            if score.score >= self.threshold + margin:
                severity = level
                lower_bound = self.threshold + margin
                upper_bound = None if next_margin is None else self.threshold + next_margin
        reasons = [
            f"Anomaly score {score.score:.6f} meets the inclusive alert threshold "
            f"{self.threshold:.6f} for model {score.model_version}.",
            f"Severity {severity.value}: score meets the {lower_bound:.6f} band cutoff.",
        ]
        return {
            "severity": severity.value,
            "policy_version": POLICY_VERSION,
            "threshold_configuration_version": self.threshold_configuration_version,
            "model_version": score.model_version,
            "score": score.score,
            "threshold": self.threshold,
            "comparator": ">=",
            "severity_lower_bound": lower_bound,
            "severity_upper_bound_exclusive": upper_bound,
            "reasons": reasons,
            "feature_definition_version": FEATURE_DEFINITION_VERSION,
            "observed_features": features.model_dump(mode="json"),
            "feature_note": "Observed context; these values are not causal model explanations.",
        }


class AlertProcessor:
    def __init__(self, policy: AlertPolicy | None = None) -> None:
        self.policy = policy

    def store(
        self,
        session: Session,
        event: TransactionEvent,
        anomaly_id: UUID,
        score: ScoreResult,
        features: TransactionFeatureVector,
    ) -> bool:
        evidence = self.policy.evaluate(score, features) if self.policy is not None else None
        if evidence is None:
            return False
        values = {
            "id": uuid4(),
            "transaction_id": event.data.transaction_id,
            "anomaly_id": anomaly_id,
            "event_id": event.event_id,
            "severity": evidence["severity"],
            "policy_version": POLICY_VERSION,
            "model_version": score.model_version,
            "evidence": evidence,
        }
        dialect = session.get_bind().dialect.name
        insert = postgres_insert if dialect == "postgresql" else sqlite_insert
        statement = (
            insert(AlertRecord)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["transaction_id", "policy_version"])
        )
        result = session.execute(statement)
        created = result.rowcount == 1
        if created:
            logger.info(
                "Alert created: severity=%s alert_id=%s", evidence["severity"], values["id"]
            )
            session.add(
                AlertAuditRecord(
                    id=uuid4(),
                    alert_id=values["id"],
                    version=1,
                    action="create",
                    actor="system:anomaly-worker",
                    reason="; ".join(evidence["reasons"]),
                    before=None,
                    after={"status": "open", "assignee": None, "version": 1},
                )
            )
        return created
