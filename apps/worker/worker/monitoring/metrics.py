from prometheus_client import Counter, Histogram

INFERENCE_LATENCY = Histogram(
    "transaction_anomaly_inference_duration_seconds",
    "Time spent producing an anomaly score for a transaction.",
    labelnames=("model_version", "status"),
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
INFERENCE_RESULTS = Counter(
    "transaction_anomaly_inference_total",
    "Transaction anomaly scoring outcomes.",
    labelnames=("model_version", "status"),
)
