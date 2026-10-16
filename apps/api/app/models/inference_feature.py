from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InferenceFeature(Base):
    __tablename__ = "inference_features"
    __table_args__ = (
        UniqueConstraint(
            "transaction_id",
            "feature_definition_version",
            name="uq_inference_features_version",
        ),
        Index("ix_inference_features_transaction_id", "transaction_id"),
        Index("ix_inference_features_event_id", "event_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    feature_definition_version: Mapped[str] = mapped_column(String(64), nullable=False)
    features: Mapped[dict[str, float | int]] = mapped_column(JSON, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
