import argparse
import random
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "worker"))

from worker.events.transaction import TransactionData, TransactionEvent
from worker.kafka.producer import TransactionEventProducer

CURRENCIES = (("US", "USD"), ("GB", "GBP"), ("DE", "EUR"), ("CA", "CAD"))
PAYMENT_METHODS = ("card", "bank_transfer", "wallet")
STATUSES = ("completed", "failed", "refunded")
STATUS_WEIGHTS = (0.82, 0.13, 0.05)


def generate_event(randomizer: random.Random) -> TransactionEvent:
    country, currency = randomizer.choice(CURRENCIES)
    now = datetime.now(UTC)
    return TransactionEvent(
        produced_at=now,
        data=TransactionData(
            transaction_id=uuid4(),
            account_id=f"acct-{randomizer.randint(1, 500):04d}",
            merchant_id=f"merchant-{randomizer.randint(1, 100):03d}",
            amount=Decimal(randomizer.randint(100, 250_000)) / 100,
            currency=currency,
            country=country,
            status=randomizer.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0],
            occurred_at=now,
            device_id=f"device-{randomizer.randint(1, 250):04d}",
            ip_address=f"198.51.100.{randomizer.randint(1, 254)}",
            payment_method=randomizer.choice(PAYMENT_METHODS),
            order_amount=Decimal(randomizer.randint(100, 250_000)) / 100,
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish generated transactions to Kafka"
    )
    parser.add_argument("--bootstrap-servers", default="127.0.0.1:9092")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be at least 1")
    if args.interval < 0:
        parser.error("--interval cannot be negative")
    return args


def main() -> None:
    args = parse_args()
    producer = TransactionEventProducer.connect(args.bootstrap_servers)
    randomizer = random.Random(args.seed)
    try:
        for sequence in range(1, args.count + 1):
            event = generate_event(randomizer)
            producer.publish(event)
            print(
                f"published {sequence}/{args.count} "
                f"event_id={event.event_id} transaction_id={event.data.transaction_id}"
            )
            if sequence < args.count:
                time.sleep(args.interval)
    finally:
        producer.close()


if __name__ == "__main__":
    main()
