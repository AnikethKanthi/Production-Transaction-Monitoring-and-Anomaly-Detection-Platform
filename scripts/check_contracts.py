"""Validate the deployed OpenAPI contract needed by the web and smoke workflows."""

from __future__ import annotations

import argparse
import json
from urllib.request import urlopen

REQUIRED_OPERATIONS = {
    "/health": {"get"},
    "/auth/me": {"get"},
    "/transactions": {"get", "post"},
    "/transactions/{transaction_id}/investigation": {"get"},
    "/alerts": {"get"},
    "/alerts/{alert_id}": {"get"},
    "/alerts/{alert_id}/acknowledge": {"post"},
    "/alerts/{alert_id}/assign": {"post"},
    "/alerts/{alert_id}/resolve": {"post"},
    "/alerts/{alert_id}/false-positive": {"post"},
    "/metrics": {"get"},
}
REQUIRED_SCHEMAS = {
    "AlertDetails": {
        "id",
        "transaction_id",
        "evidence",
        "status",
        "version",
        "audit_history",
    },
    "TransactionInvestigation": {"transaction", "anomaly", "alerts"},
    "MetricsResponse": {"overall", "by_country", "by_payment_method", "time_series"},
}


def validate(document: dict) -> None:
    paths = document.get("paths", {})
    for path, methods in REQUIRED_OPERATIONS.items():
        missing = methods - set(paths.get(path, {}))
        if missing:
            raise RuntimeError(f"OpenAPI contract missing {path}: {sorted(missing)}")
    schemas = document.get("components", {}).get("schemas", {})
    for name, required in REQUIRED_SCHEMAS.items():
        actual = set(schemas.get(name, {}).get("properties", {}))
        missing = required - actual
        if missing:
            raise RuntimeError(
                f"OpenAPI schema {name} missing fields: {sorted(missing)}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/openapi.json")
    args = parser.parse_args()
    with urlopen(args.url, timeout=10) as response:
        document = json.load(response)
    validate(document)
    print(
        f"PASS {len(REQUIRED_OPERATIONS)} operations and "
        f"{len(REQUIRED_SCHEMAS)} response schemas"
    )


if __name__ == "__main__":
    main()
