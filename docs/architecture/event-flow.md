# Event-to-alert flow

The sequence below shows the normal path from a producer publishing an event to an operator
seeing the resulting transaction or alert.

```mermaid
sequenceDiagram
    participant Producer
    participant Kafka
    participant Worker
    participant PostgreSQL
    participant API
    participant UI
    Producer->>Kafka: transaction.created v1
    Kafka->>Worker: record + partition/offset
    Worker->>Worker: validate and build transaction_features.v1
    Worker->>Worker: score with isolation_forest.v1
    Worker->>PostgreSQL: transaction + receipt + features + anomaly + optional alert
    PostgreSQL-->>Worker: commit
    Worker->>Kafka: manual offset commit
    UI->>API: GET transaction investigation
    API->>PostgreSQL: transaction, anomaly, alerts
    API-->>UI: evidence and model version
    UI->>API: POST alert resolve(expected_version)
    API->>PostgreSQL: atomic versioned update + audit row
    API-->>UI: resolved alert
```

Transient PostgreSQL failures are retried with capped full-jitter backoff and leave the Kafka offset uncommitted after exhaustion so supervision can restart and replay. Permanently malformed records are wrapped with topic, partition, offset, original bytes, attempts, and safe error metadata and published to `transactions.v1.dlq` before the source offset is committed. Replaying an already committed event returns `duplicate` and writes no second transaction, feature vector, anomaly, alert, or audit record.

The feature history query and final persistence occur in one database transaction. Events for the same account should be produced in business order; the end-to-end fixture explicitly waits for history persistence because Kafka ordering is only guaranteed within a partition.
