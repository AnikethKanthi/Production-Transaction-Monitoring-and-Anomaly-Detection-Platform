from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Anomaly, Transaction


class MetricsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def aggregate(
        self, start: datetime, end: datetime, interval: str, currency: str | None
    ) -> dict:
        return {
            "overall": self._rows(start, end, currency, None)[0],
            "by_country": self._rows(start, end, currency, Transaction.country),
            "by_payment_method": self._rows(
                start, end, currency, func.coalesce(Transaction.payment_method, "unknown")
            ),
            "time_series": self._rows(
                start, end, currency, func.date_trunc(interval, Transaction.occurred_at)
            ),
        }

    def _rows(self, start: datetime, end: datetime, currency: str | None, group) -> list[dict]:
        columns = [
            func.count(Transaction.id).label("transaction_count"),
            func.coalesce(func.sum(Transaction.amount), 0).label("transaction_amount"),
            func.coalesce(func.avg(Transaction.amount), 0).label("average_transaction_amount"),
            func.sum(case((Transaction.status == "completed", 1), else_=0)).label("successes"),
            func.sum(case((Transaction.status == "failed", 1), else_=0)).label("declines"),
            func.sum(case((Transaction.status == "refunded", 1), else_=0)).label("refunds"),
            func.sum(
                case(((Anomaly.scoring_status == "scored") & (Anomaly.score > 0), 1), else_=0)
            ).label("anomalies"),
            func.coalesce(func.avg(Anomaly.inference_latency_seconds), 0).label(
                "average_processing_latency_seconds"
            ),
        ]
        if group is not None:
            columns.insert(0, group.label("label"))
        statement = (
            select(*columns)
            .select_from(Transaction)
            .outerjoin(Anomaly, Anomaly.transaction_id == Transaction.id)
            .where(Transaction.occurred_at >= start, Transaction.occurred_at < end)
        )
        if currency is not None:
            statement = statement.where(Transaction.currency == currency)
        if group is not None:
            statement = statement.group_by(group).order_by(group)
        rows = self.session.execute(statement).mappings().all()
        return [dict(row) | ({"label": "all"} if group is None else {}) for row in rows]
