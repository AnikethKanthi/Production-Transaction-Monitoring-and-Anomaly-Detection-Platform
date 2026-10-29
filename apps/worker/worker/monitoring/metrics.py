import json
import logging

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

INFERENCE_LATENCY = Histogram(
    "transaction_anomaly_inference_duration_seconds",
    "Time spent producing an anomaly score for a transaction.",
    labelnames=("status",),
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
INFERENCE_RESULTS = Counter(
    "transaction_anomaly_inference_total",
    "Transaction anomaly scoring outcomes.",
    labelnames=("status",),
)

WORKER_EVENTS = Counter(
    "worker_transaction_events_total", "Durably handled Kafka messages.", ("outcome",)
)
WORKER_RETRIES = Counter("worker_processing_failures_total", "Failed processing attempts.")
WORKER_LATENCY = Histogram("worker_message_duration_seconds", "Message handling including retries.")
KAFKA_LAG = Gauge(
    "worker_kafka_consumer_lag",
    "High watermark minus committed offsets summed over known partitions.",
)
KAFKA_KNOWN_PARTITIONS = Gauge(
    "worker_kafka_lag_known_partitions",
    "Partitions with known committed lag in last statistics update.",
)
KAFKA_STATS_TIME = Gauge(
    "worker_kafka_statistics_timestamp_seconds", "Time of last valid Kafka statistics update."
)


def kafka_statistics(payload: str) -> None:
    """Sum fixed-topic committed lag without per-partition or client-ID labels."""
    try:
        stats = json.loads(payload)
        partitions = stats.get("topics", {}).get("transactions.v1", {}).get("partitions", {})
        lag, known = 0, 0
        for partition_id, partition in partitions.items():
            if int(partition_id) < 0:
                continue
            high = partition.get("hi_offset", -1)
            committed = partition.get("committed_offset", -1)
            if isinstance(high, (int, float)) and isinstance(committed, (int, float)):
                if high >= 0 and committed >= 0:
                    lag += max(0, high - committed)
                    known += 1
        KAFKA_LAG.set(lag)
        KAFKA_KNOWN_PARTITIONS.set(known)
        KAFKA_STATS_TIME.set_to_current_time()
    except (ValueError, TypeError, AttributeError):
        logger.warning("Invalid Kafka statistics callback payload")
