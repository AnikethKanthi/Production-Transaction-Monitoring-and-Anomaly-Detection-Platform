from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProcessedEvent(Base):
    __tablename__ = "processed_events"
    __table_args__ = (
        Index("ix_processed_events_transaction_id", "transaction_id"),
        Index("ix_processed_events_processed_at", "processed_at"),
    )

    # Required producer-supplied identifier: never generate it during processing.
    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
