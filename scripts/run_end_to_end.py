"""Exercise the real Kafka-to-dashboard alert workflow against a disposable stack."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from worker.events.transaction import TransactionData, TransactionEvent
from worker.kafka.producer import TransactionEventProducer

HISTORY_COUNT = 12
POLL_SECONDS = 90


class ApiClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, body: dict | None = None) -> Any:
        data = None if body is None else json.dumps(body).encode()
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
                **({"Content-Type": "application/json"} if data else {}),
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(
                f"API returned HTTP {error.code} for {method} {path}"
            ) from error
        except URLError as error:
            raise RuntimeError(f"API unavailable for {method} {path}") from error


def anomaly_sequence(now: datetime) -> list[TransactionEvent]:
    """Build history plus a deterministic outlier that exercises feature transformation."""
    account_id = f"e2e-account-{uuid4()}"
    anchor = now.replace(hour=1, minute=30, second=0, microsecond=0)
    if anchor > now:
        anchor -= timedelta(days=1)
    start = anchor - timedelta(minutes=HISTORY_COUNT + 1)
    events: list[TransactionEvent] = []
    for index in range(HISTORY_COUNT):
        occurred_at = start + timedelta(minutes=index)
        events.append(
            TransactionEvent(
                produced_at=now,
                correlation_id=f"e2e-history-{index}",
                data=TransactionData(
                    transaction_id=uuid4(),
                    account_id=account_id,
                    merchant_id="e2e-baseline-merchant",
                    amount=Decimal("25.00"),
                    currency="USD",
                    country="US",
                    status="failed",
                    occurred_at=occurred_at,
                    device_id="e2e-known-device",
                    ip_address="198.51.100.10",
                    payment_method="card",
                    order_amount=Decimal("25.00"),
                ),
            )
        )
    events.append(
        TransactionEvent(
            produced_at=now,
            correlation_id="e2e-target-anomaly",
            data=TransactionData(
                transaction_id=uuid4(),
                account_id=account_id,
                merchant_id="e2e-outlier-merchant",
                amount=Decimal("50000.00"),
                currency="USD",
                country="GB",
                status="completed",
                occurred_at=anchor,
                device_id="e2e-new-device",
                ip_address="203.0.113.250",
                payment_method="wallet",
                order_amount=Decimal("70000.00"),
            ),
        )
    )
    return events


def wait_for_alert(client: ApiClient, transaction_id: UUID) -> dict:
    deadline = time.monotonic() + POLL_SECONDS
    path = f"/transactions/{transaction_id}/investigation"
    last_state = "transaction not available"
    while time.monotonic() < deadline:
        try:
            investigation = client.request("GET", path)
            anomaly = investigation.get("anomaly")
            alerts = investigation.get("alerts", [])
            if anomaly and anomaly.get("scoring_status") != "scored":
                raise RuntimeError(
                    "worker used fallback scoring instead of the committed model"
                )
            if alerts:
                return {"investigation": investigation, "alert": alerts[0]}
            last_state = "transaction persisted but no alert was created"
        except RuntimeError as error:
            if "HTTP 404" not in str(error):
                raise
        time.sleep(1)
    raise RuntimeError(f"Timed out after {POLL_SECONDS}s: {last_state}")


def wait_for_transaction(client: ApiClient, transaction_id: UUID) -> None:
    deadline = time.monotonic() + POLL_SECONDS
    while time.monotonic() < deadline:
        try:
            transaction = client.request("GET", f"/transactions/{transaction_id}")
            if transaction.get("id") == str(transaction_id):
                return
        except RuntimeError as error:
            if "HTTP 404" not in str(error):
                raise
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for transaction {transaction_id}")


def prepare(args: argparse.Namespace) -> None:
    token_path = args.token_file.resolve()
    token = token_path.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise RuntimeError("token file does not contain a valid access token")
    events = anomaly_sequence(datetime.now(UTC))
    client = ApiClient(args.api_url, token)
    producer = TransactionEventProducer.connect(args.bootstrap_servers)
    try:
        for event in events[:-1]:
            producer.publish(event)
            # Transaction IDs are Kafka keys and can map to different partitions.
            # Persist each history row before the target to make feature history deterministic.
            wait_for_transaction(client, event.data.transaction_id)
        producer.publish(events[-1])
    finally:
        producer.close()

    target = events[-1]
    result = wait_for_alert(client, target.data.transaction_id)
    anomaly = result["investigation"]["anomaly"]
    alert = result["alert"]
    if alert["transaction_id"] != str(target.data.transaction_id):
        raise RuntimeError("alert contract returned a different transaction")
    context = {
        "schema_version": 1,
        "transaction_id": str(target.data.transaction_id),
        "event_id": str(target.event_id),
        "alert_id": alert["id"],
        "initial_alert_version": alert["version"],
        "model_version": anomaly["model_version"],
        "anomaly_score": anomaly["score"],
        "token_file": str(token_path),
    }
    args.context.parent.mkdir(parents=True, exist_ok=True)
    args.context.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "result": "prepared",
                "model_version": anomaly["model_version"],
                "alert_severity": alert["severity"],
                "published_events": len(events),
            },
            sort_keys=True,
        )
    )


def verify(args: argparse.Namespace) -> None:
    context = json.loads(args.context.read_text(encoding="utf-8"))
    token = Path(context["token_file"]).read_text(encoding="utf-8").strip()
    client = ApiClient(args.api_url, token)
    details = client.request("GET", f"/alerts/{context['alert_id']}")
    if details["status"] != "resolved":
        raise RuntimeError("browser workflow did not resolve the alert")
    audit = details.get("audit_history", [])
    actions = [entry.get("action") for entry in audit]
    if actions[:1] != ["create"] or actions[-1:] != ["resolve"]:
        raise RuntimeError(f"alert audit contract is incomplete: {actions}")
    investigation = client.request(
        "GET", f"/transactions/{context['transaction_id']}/investigation"
    )
    if investigation["anomaly"]["model_version"] != context["model_version"]:
        raise RuntimeError("model version changed between preparation and verification")
    if investigation["alerts"][0]["status"] != "resolved":
        raise RuntimeError(
            "resolved state is not visible through transaction investigation"
        )
    print(json.dumps({"result": "verified", "audit_actions": actions}, sort_keys=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "verify"))
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--bootstrap-servers", default="127.0.0.1:9092")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--context", type=Path, default=Path(".local/e2e-context.json"))
    args = parser.parse_args()
    if args.phase == "prepare" and args.token_file is None:
        parser.error("prepare requires --token-file")
    if not args.api_url.startswith("http://127.0.0.1:"):
        parser.error("--api-url must target a loopback disposable stack")
    return args


if __name__ == "__main__":
    arguments = parse_args()
    prepare(arguments) if arguments.phase == "prepare" else verify(arguments)
