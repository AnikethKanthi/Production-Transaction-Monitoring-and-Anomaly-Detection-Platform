# Kafka event contracts

Producers and consumers use these contracts as their shared source of truth. If an event
changes, update the schema, runtime validation, tests, and this document together.

## Topics

| Topic | Partitions | Producer | Consumer | Retention meaning |
| --- | ---: | --- | --- | --- |
| `transactions.v1` | 3 | transaction producers | `transaction-processor-v1` | Source transaction events |
| `transactions.v1.dlq` | 3 | transaction worker | recovery tooling/operators | Permanently invalid records plus replay metadata |

The repository schemas under `contracts/events/` are JSON Schema 2020-12. Runtime ingestion currently consumes `transaction.created` version `1`; the alert/anomaly/update schemas are reserved integration contracts and are not published by the current worker.

## `transaction.created` v1

Kafka key is the UTF-8 transaction UUID. Required envelope fields are `event_id`, `event_type`, `event_version`, `produced_at`, and `data`. `event_id` is the idempotency key and must be reused for retries. Times require offsets. Amounts are decimal strings with at most two fractional digits. Country and currency are uppercase two- and three-letter codes. Unknown fields are rejected.

```json
{
  "event_id": "7abf6ea1-a8b4-45f5-b638-43865b69af87",
  "event_type": "transaction.created",
  "event_version": 1,
  "produced_at": "2026-11-10T08:30:00Z",
  "correlation_id": "demo-001",
  "data": {
    "transaction_id": "43669512-403d-4a19-84dc-653ba486378a",
    "account_id": "acct-demo",
    "merchant_id": "merchant-demo",
    "amount": "50000.00",
    "currency": "USD",
    "country": "US",
    "status": "completed",
    "occurred_at": "2026-11-10T08:29:58Z",
    "device_id": "device-new",
    "ip_address": "203.0.113.20",
    "payment_method": "card",
    "order_amount": "50000.00"
  }
}
```

## Dead-letter v1

The DLQ wrapper preserves source topic, partition, offset, Base64 key/payload, recovered event ID when possible, attempts, safe error type/message, and failure time. Consumers must treat original bytes as untrusted and must not log decoded payment payloads. Retry or replay only after correcting the cause; retain the original `event_id`. See [Kafka replay](runbooks/kafka-replay.md).
