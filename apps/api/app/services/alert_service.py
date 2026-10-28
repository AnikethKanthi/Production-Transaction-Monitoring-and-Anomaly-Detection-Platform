from uuid import UUID, uuid4

from app.db.repositories.alerts import AlertRepository
from app.models import AlertAudit
from app.schemas.alert import AlertAssignment, AlertMutation


class AlertWorkflowError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        self.code, self.message, self.status_code = code, message, status_code
        super().__init__(message)


class AlertService:
    def __init__(self, repository: AlertRepository) -> None:
        self.repository = repository

    def get(self, alert_id: UUID):
        alert = self.repository.get(alert_id)
        if alert is None:
            raise AlertWorkflowError("alert_not_found", f"Alert {alert_id} was not found", 404)
        return alert

    def mutate(self, alert_id: UUID, action: str, payload: AlertMutation):
        alert = self.get(alert_id)
        if alert.version != payload.expected_version:
            raise AlertWorkflowError("alert_version_conflict", "Alert changed; reload and retry")
        before = {"status": alert.status, "assignee": alert.assignee, "version": alert.version}
        if alert.status in {"resolved", "false_positive"}:
            raise AlertWorkflowError("invalid_alert_transition", "Closed alerts cannot be modified")
        changes = {}
        if action == "assign" and isinstance(payload, AlertAssignment):
            if alert.assignee == payload.assignee:
                raise AlertWorkflowError(
                    "invalid_alert_transition", "Alert already has that assignee"
                )
            changes["assignee"] = payload.assignee
        elif action == "acknowledge" and alert.status == "open":
            changes["status"] = "acknowledged"
        elif action in {"resolve", "false-positive"}:
            changes["status"] = "resolved" if action == "resolve" else "false_positive"
        else:
            raise AlertWorkflowError(
                "invalid_alert_transition", "Action is not allowed from this status"
            )
        if not self.repository.compare_and_update(alert_id, payload.expected_version, changes):
            raise AlertWorkflowError("alert_version_conflict", "Alert changed; reload and retry")
        self.repository.session.refresh(alert)
        self.repository.session.add(
            AlertAudit(
                id=uuid4(),
                alert_id=alert.id,
                version=alert.version,
                action=action,
                actor=payload.actor,
                reason=payload.reason,
                before=before,
                after={
                    "status": alert.status,
                    "assignee": alert.assignee,
                    "version": alert.version,
                },
            )
        )
        self.repository.session.flush()
        return alert
