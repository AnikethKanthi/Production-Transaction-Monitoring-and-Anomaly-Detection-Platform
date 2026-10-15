import base64
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class DeadLetterEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dead_letter_id: UUID = Field(default_factory=uuid4)
    failed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    original_topic: str
    original_partition: int
    original_offset: int
    original_key_base64: str | None
    original_payload_base64: str
    event_id: UUID | None = None
    attempts: int = Field(ge=1)
    error_type: str
    error_message: str

    @classmethod
    def from_message(
        cls,
        *,
        topic: str,
        partition: int,
        offset: int,
        key: bytes | None,
        payload: bytes,
        event_id: UUID | None,
        attempts: int,
        error: Exception,
    ) -> "DeadLetterEvent":
        return cls(
            original_topic=topic,
            original_partition=partition,
            original_offset=offset,
            original_key_base64=base64.b64encode(key).decode() if key is not None else None,
            original_payload_base64=base64.b64encode(payload).decode(),
            event_id=event_id,
            attempts=attempts,
            error_type=type(error).__name__,
            error_message=str(error),
        )


def serialize_dead_letter_event(event: DeadLetterEvent) -> bytes:
    return event.model_dump_json().encode("utf-8")
