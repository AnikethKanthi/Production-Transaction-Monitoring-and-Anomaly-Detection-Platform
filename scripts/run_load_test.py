"""Bounded HTTP transaction load or Kafka-to-database pipeline measurement."""

import argparse
import asyncio
import json
import logging
import math
import os
import random
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from performance_common import distribution, save_report


def worker_snapshot(url="http://127.0.0.1:9101/metrics"):
    from prometheus_client.parser import text_string_to_metric_families

    try:
        response = httpx.get(url, timeout=2)
        response.raise_for_status()
        samples = {
            sample.name: sample.value
            for family in text_string_to_metric_families(response.text)
            for sample in family.samples
            if not sample.labels
        }
        duplicate = next(
            (
                sample.value
                for family in text_string_to_metric_families(response.text)
                for sample in family.samples
                if sample.name == "worker_transaction_events_total"
                and sample.labels.get("outcome") == "duplicate"
            ),
            0,
        )
        stamp = samples.get("worker_kafka_statistics_timestamp_seconds", 0)
        return {
            "available": True,
            "lag": samples.get("worker_kafka_consumer_lag"),
            "known_partitions": samples.get("worker_kafka_lag_known_partitions", 0),
            "statistics_age_seconds": time.time() - stamp,
            "duplicates": duplicate,
        }
    except (httpx.HTTPError, ValueError):
        return {"available": False}


async def api_load(base_url, token, count, concurrency, rate, operation="mixed"):
    timings, successes, statuses = defaultdict(list), defaultdict(list), Counter()
    queue = asyncio.Queue(maxsize=concurrency * 2)
    started = time.perf_counter()
    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=8,
        limits=httpx.Limits(max_connections=concurrency),
    ) as client:

        async def worker():
            while (index := await queue.get()) is not None:
                method, path, body = "GET", "/transactions?limit=20", None
                if operation == "create" or (operation == "mixed" and index % 5 == 0):
                    method, path = "POST", "/transactions"
                    body = {
                        "account_id": "load-test",
                        "amount": "12.34",
                        "country": "US",
                        "currency": "USD",
                        "status": "completed",
                        "occurred_at": datetime.now(UTC).isoformat(),
                    }
                elif index % 2:
                    path = "/alerts?limit=20"
                label = method + " " + path
                before = time.perf_counter()
                try:
                    response = await client.request(method, path, json=body)
                    status = response.status_code
                    if 200 <= status < 300:
                        try:
                            body = response.json()
                            valid = isinstance(body, dict) and (
                                isinstance(body.get("id"), str)
                                if method == "POST"
                                else isinstance(body.get("items"), list)
                                and isinstance(body.get("pagination"), dict)
                            )
                        except ValueError:
                            valid = False
                        if not valid:
                            status = "invalid_response"
                except httpx.HTTPError:
                    status = "transport_error"
                elapsed = (time.perf_counter() - before) * 1000
                statuses[str(status)] += 1
                timings[label].append(elapsed)
                if isinstance(status, int) and 200 <= status < 300:
                    successes[label].append(elapsed)
                queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
        for index in range(count):
            await asyncio.sleep(max(0, started + index / rate - time.perf_counter()))
            await queue.put(index)
        await queue.join()
        for _ in workers:
            await queue.put(None)
        await asyncio.gather(*workers)
    elapsed = time.perf_counter() - started
    errors = sum(value for key, value in statuses.items() if not key.startswith("2"))
    return {
        "kind": "live_http",
        "requests": count,
        "concurrency": concurrency,
        "offered_requests_per_second": rate,
        "elapsed_seconds": elapsed,
        "completed_requests_per_second": count / elapsed,
        "successful_requests_per_second": (count - errors) / elapsed,
        "error_count": errors,
        "statuses": dict(statuses),
        "latency_ms": {key: distribution(value) for key, value in timings.items()},
        "successful_latency_ms": {
            key: distribution(value) for key, value in successes.items()
        },
        "api_p95_under_300ms": errors == 0
        and all(distribution(v)["p95"] < 300 for v in timings.values()),
    }


def publish(events, bootstrap):
    from confluent_kafka import Producer

    producer = Producer(
        {
            "bootstrap.servers": bootstrap,
            "enable.idempotence": True,
            "acks": "all",
            "linger.ms": 5,
            "batch.size": 65536,
            "message.timeout.ms": 10000,
            "socket.timeout.ms": 5000,
        }
    )
    errors = []

    def delivered(error, _message):
        if error is not None:
            errors.append(type(error).__name__)

    for event in events:
        producer.produce(
            "transactions.v1",
            key=str(event.data.transaction_id),
            value=event.model_dump_json().encode(),
            on_delivery=delivered,
        )
        producer.poll(0)
    if producer.flush(15) or errors:
        raise RuntimeError(
            "Kafka delivery failed or timed out; preserve the manifest for replay"
        )


def pipeline_snapshot(engine, events):
    from sqlalchemy import select

    # Chunk to keep parameters bounded; no join multiplying alerts/transactions.
    from sqlalchemy.orm import Session
    from worker.persistence.models import (
        AlertRecord,
        AnomalyRecord,
        ProcessedEventRecord,
    )

    scored, alerts, processed = [], [], set()
    with Session(engine) as session:
        for start in range(0, len(events), 500):
            chunk = events[start : start + 500]
            ids = [event.data.transaction_id for event in chunk]
            scored.extend(
                session.scalars(
                    select(AnomalyRecord).where(AnomalyRecord.transaction_id.in_(ids))
                )
            )
            alerts.extend(
                session.scalars(
                    select(AlertRecord).where(AlertRecord.transaction_id.in_(ids))
                )
            )
            processed.update(
                session.scalars(
                    select(ProcessedEventRecord.event_id).where(
                        ProcessedEventRecord.event_id.in_(
                            [event.event_id for event in chunk]
                        )
                    )
                )
            )
    return scored, alerts, processed


def kafka_load(args):
    from app.db.session import get_engine
    from generate_transactions import generate_event
    from worker.events.transaction import TransactionEvent

    manifest = Path(args.manifest)
    if args.replay:
        events = [
            TransactionEvent.model_validate_json(line)
            for line in manifest.read_text().splitlines()
        ]
    else:
        if manifest.exists():
            raise ValueError("Manifest exists; use --replay or a fresh path")
        randomizer = random.Random(args.seed)
        events = [generate_event(randomizer) for _ in range(args.count)]
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            "\n".join(event.model_dump_json() for event in events) + "\n"
        )
    if not events or len(events) > 10000:
        raise ValueError("Kafka manifest must contain 1..10000 events")
    if len({event.event_id for event in events}) != len(events):
        raise ValueError(
            "Manifest event IDs must be unique; --replay preserves existing IDs"
        )
    before = time.perf_counter()
    publish(events, args.bootstrap_servers)
    deadline = before + args.timeout
    lag_samples = []
    while True:
        scored, alerts, processed = pipeline_snapshot(get_engine(), events)
        measurement = worker_snapshot()
        if (
            measurement.get("available")
            and measurement.get("known_partitions", 0) > 0
            and measurement.get("statistics_age_seconds", 999) < 60
        ):
            lag_samples.append(measurement["lag"])
        if (
            len(processed) == len({event.event_id for event in events})
            or time.perf_counter() >= deadline
        ):
            break
        time.sleep(0.25)
    elapsed = time.perf_counter() - before
    produced = {event.data.transaction_id: event.produced_at for event in events}
    alert_seconds = [
        (alert.created_at - produced[alert.transaction_id]).total_seconds()
        for alert in alerts
    ]
    latencies = [
        score.inference_latency_seconds * 1000
        for score in scored
        if score.scoring_status == "scored"
    ]
    from worker.config import Settings
    from worker.processors.alert_processor import AlertPolicy

    settings = Settings()
    policy = AlertPolicy.load(settings.alert_threshold_path, settings.model_path)
    expected_alerts = {
        score.transaction_id
        for score in scored
        if policy is not None
        and score.scoring_status == "scored"
        and score.model_version == policy.model_version
        and score.score >= policy.threshold
    }
    actual_alerts = {alert.transaction_id for alert in alerts}
    return {
        "kind": "live_kafka_pipeline",
        "replay": args.replay,
        "published": len(events),
        "processed_event_ids": len(processed),
        "scored_transactions": len(scored),
        "alerts": len(alerts),
        "qualifying_transactions": len(expected_alerts),
        "threshold_configuration_available": policy is not None,
        "qualifying_alerts_present": None
        if policy is None
        else expected_alerts.issubset(actual_alerts),
        "elapsed_seconds": elapsed,
        "observed_events_per_second": None if args.replay else len(processed) / elapsed,
        "inference_ms": distribution(latencies),
        "alert_creation_seconds": distribution(alert_seconds),
        "consumer_lag": {
            "valid_samples": len(lag_samples),
            "max": max(lag_samples) if lag_samples else None,
            "last": lag_samples[-1] if lag_samples else None,
        },
        "fallback_scores": sum(score.scoring_status == "fallback" for score in scored),
        "active_model_scoring": bool(scored)
        and all(score.scoring_status == "scored" for score in scored),
        "model_versions": sorted({score.model_version for score in scored}),
        "all_events_processed": len(processed) == len(events),
        "alerts_under_10s": None
        if args.replay or not alerts
        else all(0 <= value < 10 for value in alert_seconds),
        "note": "Replay completion requires the separate offset/duplicate-counter recovery drill; rows may preexist.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["api", "kafka"], default="api")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--rate", type=float, default=10)
    parser.add_argument(
        "--operation", choices=["read", "create", "mixed"], default="mixed"
    )
    parser.add_argument("--bootstrap-servers", default="127.0.0.1:9092")
    parser.add_argument("--manifest", default=".local/load-events.jsonl")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--report", default=".local/performance.json")
    args = parser.parse_args()
    if (
        not 1 <= args.count <= 10000
        or not 1 <= args.concurrency <= 100
        or args.rate <= 0
        or not math.isfinite(args.rate)
        or not 1 <= args.timeout <= 600
    ):
        parser.error(
            "count 1..10000, concurrency 1..100, positive rate, timeout 1..600 required"
        )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.mode == "api":
        url = urlsplit(args.base_url)
        if url.username or url.password or url.query or url.fragment:
            parser.error("Use a base URL without credentials, query or fragment")
        if url.scheme != "https" and url.hostname not in {"127.0.0.1", "localhost"}:
            parser.error("Remote loads require HTTPS")
        token = (
            args.token_file.read_text().strip()
            if args.token_file
            else os.environ.get("LOAD_TEST_TOKEN")
        )
        if not token:
            parser.error(
                "Provide --token-file or LOAD_TEST_TOKEN; never put tokens in arguments"
            )
        report = asyncio.run(
            api_load(
                args.base_url,
                token,
                args.count,
                args.concurrency,
                args.rate,
                args.operation,
            )
        )
    else:
        report = kafka_load(args)
    report["recorded_at"] = datetime.now(UTC).isoformat()
    save_report(args.report, report)
    print(json.dumps(report, indent=2))
    if (
        report.get("api_p95_under_300ms") is False
        or report.get("all_events_processed") is False
        or report.get("alerts_under_10s") is False
        or report.get("qualifying_alerts_present") is False
        or report.get("active_model_scoring") is False
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
