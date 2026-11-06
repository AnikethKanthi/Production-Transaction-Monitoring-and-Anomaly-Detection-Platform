"""Collect real PostgreSQL query plans; compare reports before/after a migration."""

import argparse

from app.db.session import get_engine
from performance_common import save_report
from sqlalchemy import text

QUERIES = {
    "transaction_status_page": "SELECT * FROM transactions WHERE status='completed' ORDER BY occurred_at DESC, id DESC LIMIT 20",
    "transaction_currency_page": "SELECT * FROM transactions WHERE currency='USD' ORDER BY occurred_at DESC, id DESC LIMIT 20",
    "open_alert_queue": "SELECT * FROM alerts WHERE status='open' ORDER BY created_at DESC, id DESC LIMIT 20",
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=".local/query-plans.json")
    parser.add_argument("--refresh-statistics", action="store_true")
    args = parser.parse_args()
    with get_engine().begin() as connection:
        if args.refresh_statistics:
            connection.execute(text("ANALYZE transactions"))
            connection.execute(text("ANALYZE alerts"))
        plans = {
            name: connection.scalar(
                text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query)
            )
            for name, query in QUERIES.items()
        }
    save_report(args.report, plans)
    print(
        "Query-plan report saved; small fixtures may legitimately use sequential scans."
    )
