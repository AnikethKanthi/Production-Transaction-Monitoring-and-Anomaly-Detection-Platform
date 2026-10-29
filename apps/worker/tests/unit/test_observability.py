import json
import logging
from datetime import UTC, datetime
from unittest.mock import Mock
from urllib.request import urlopen
from uuid import uuid4

from prometheus_client import generate_latest, start_http_server
from prometheus_client.parser import text_string_to_metric_families

from worker.consumers.transaction_consumer import TransactionConsumer
from worker.events.transaction import TransactionData, TransactionEvent, serialize_transaction_event
from worker.logging import JsonFormatter, event_context, log_context
from worker.monitoring.metrics import (
    KAFKA_KNOWN_PARTITIONS,
    KAFKA_LAG,
    WORKER_EVENTS,
    kafka_statistics,
)


def event():
    return TransactionEvent(
        produced_at=datetime.now(UTC),
        correlation_id="api-trace-17",
        data=TransactionData(
            transaction_id=uuid4(),
            account_id="acct-1",
            amount="10",
            country="US",
            currency="USD",
            status="completed",
            occurred_at=datetime.now(UTC),
        ),
    )


def test_context_is_structured_and_cleared_after_worker_event():
    candidate = event()
    with event_context(candidate):
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "Processed", (), None)
        value = json.loads(JsonFormatter().format(record))
        assert value["correlation_id"] == "api-trace-17"
        assert value["event_id"] == str(candidate.event_id)
        assert value["transaction_id"] == str(candidate.data.transaction_id)
    assert log_context.get() == {}


def test_throughput_counts_committed_messages_only():
    candidate = event()
    message = Mock()
    message.value.return_value = serialize_transaction_event(candidate)
    client = Mock()
    observed = []
    processor = Mock(side_effect=lambda _: observed.append(dict(log_context.get())))
    count = WORKER_EVENTS.labels("processed")._value.get()
    consumer = TransactionConsumer(client, processor, Mock())
    consumer._handle(message)
    assert observed[0]["event_id"] == str(candidate.event_id)
    assert WORKER_EVENTS.labels("processed")._value.get() == count + 1
    assert log_context.get() == {}
    client.commit.side_effect = RuntimeError("commit failed")
    import pytest

    with pytest.raises(RuntimeError):
        consumer._handle(message)
    assert WORKER_EVENTS.labels("processed")._value.get() == count + 1
    assert log_context.get() == {}


def test_kafka_committed_lag_aggregates_without_partition_labels():
    kafka_statistics(
        json.dumps(
            {
                "topics": {
                    "transactions.v1": {
                        "partitions": {
                            "0": {"hi_offset": 120, "committed_offset": 100},
                            "1": {"hi_offset": 50, "committed_offset": 45},
                            "2": {"hi_offset": 30, "committed_offset": -1001},
                            "-1": {"hi_offset": 900, "committed_offset": 0},
                        }
                    }
                }
            }
        )
    )
    assert KAFKA_LAG._value.get() == 25
    assert KAFKA_KNOWN_PARTITIONS._value.get() == 2
    kafka_statistics("bad json")
    kafka_statistics(json.dumps({"topics": {}}))
    assert KAFKA_LAG._value.get() == 0
    assert KAFKA_KNOWN_PARTITIONS._value.get() == 0
    for metric in ("worker_kafka_consumer_lag", "worker_kafka_lag_known_partitions"):
        assert f"{metric}{{" not in generate_latest().decode()


def test_worker_exposes_scrapable_http_metrics():
    server, thread = start_http_server(0, addr="127.0.0.1")
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/metrics", timeout=5) as response:
            assert response.status == 200
            metrics = {
                item.name for item in text_string_to_metric_families(response.read().decode())
            }
        assert "worker_kafka_consumer_lag" in metrics
        assert "worker_message_duration_seconds" in metrics
        assert "transaction_anomaly_inference_duration_seconds" in metrics
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
