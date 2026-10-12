from uuid import UUID

from sqlalchemy.orm import Session

from app.models import ProcessedEvent


class ProcessedEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, event: ProcessedEvent) -> ProcessedEvent:
        """Flush without committing. Duplicate IDs raise SQLAlchemy IntegrityError.

        Record the event and transaction changes in the same unit of work.
        Roll back that unit of work if a constraint fails.
        """
        self.session.add(event)
        self.session.flush()
        return event

    def get(self, event_id: UUID) -> ProcessedEvent | None:
        return self.session.get(ProcessedEvent, event_id)
