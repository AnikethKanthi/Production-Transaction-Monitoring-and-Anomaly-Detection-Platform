from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Alert, AlertAudit


class AlertRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, alert_id: UUID) -> Alert | None:
        return self.session.get(Alert, alert_id)

    def list(self, status=None, severity=None, limit=50, offset=0):
        statement = select(Alert)
        if status is not None:
            statement = statement.where(Alert.status == status)
        if severity is not None:
            statement = statement.where(Alert.severity == severity)
        total = self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = list(
            self.session.scalars(
                statement.order_by(Alert.created_at.desc(), Alert.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def compare_and_update(self, alert_id: UUID, version: int, changes: dict) -> bool:
        result = self.session.execute(
            update(Alert)
            .where(Alert.id == alert_id, Alert.version == version)
            .values(**changes, version=version + 1, updated_at=func.now())
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def audit(self, alert_id: UUID) -> list[AlertAudit]:
        return list(
            self.session.scalars(
                select(AlertAudit)
                .where(AlertAudit.alert_id == alert_id)
                .order_by(AlertAudit.version)
            )
        )
