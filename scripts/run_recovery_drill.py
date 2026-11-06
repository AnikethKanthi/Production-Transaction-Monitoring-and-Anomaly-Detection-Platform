"""Replay, interruption, and backup/restore checks for a disposable drill-* Compose project."""

import argparse
import hashlib
import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from performance_common import save_report
from run_load_test import pipeline_snapshot, publish, worker_snapshot

TABLES = (
    "transactions",
    "processed_events",
    "inference_features",
    "anomalies",
    "alerts",
    "alert_audit",
    "alembic_version",
)


class Drill:
    def __init__(self, project):
        if not re.fullmatch(r"drill-[a-z0-9-]{1,40}", project):
            raise ValueError("Recovery testing requires a disposable drill-* project")
        self.compose = ["docker", "compose", "-p", project]

    def command(self, args, **kwargs):
        result = subprocess.run(
            args, stderr=subprocess.PIPE, timeout=180, check=False, **kwargs
        )
        if result.returncode:
            # CLI error output can contain connection/user data; never echo it.
            raise RuntimeError(
                "Recovery subprocess failed; inspect service health privately"
            )
        return result.stdout

    def service(self, action, name):
        self.command(self.compose + [action, name], stdout=subprocess.PIPE)

    def validate_ports(self):
        for service, port in (("postgres", 5432), ("kafka", 9092), ("worker", 9101)):
            address = (
                self.command(
                    self.compose + ["port", service, str(port)], stdout=subprocess.PIPE
                )
                .decode()
                .strip()
            )
            if address != f"127.0.0.1:{port}":
                raise ValueError(
                    "Drill requires its own services on the default loopback ports"
                )

    def pg(self, tool, *args, **kwargs):
        return self.command(
            self.compose
            + [
                "exec",
                "-T",
                "postgres",
                "sh",
                "-ec",
                'export PGPASSWORD="$POSTGRES_PASSWORD"; exec "$@" -U "$POSTGRES_USER"',
                "sh",
                tool,
                *args,
            ],
            **kwargs,
        )

    def fingerprint(self, database):
        result = {}
        for table in TABLES:
            sql = (
                f"SELECT count(*), md5(COALESCE(string_agg(row_to_json(t)::text, "
                f"E'\\n' ORDER BY row_to_json(t)::text), '')) FROM public.{table} t"
            )
            result[table] = (
                self.pg(
                    "psql",
                    "-At",
                    "--dbname",
                    database,
                    "-c",
                    sql,
                    stdout=subprocess.PIPE,
                )
                .decode()
                .strip()
            )
        # Check indexes/constraints as well as row contents, not only counts.
        result["indexes"] = (
            self.pg(
                "psql",
                "-At",
                "--dbname",
                database,
                "-c",
                "SELECT indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY indexname",
                stdout=subprocess.PIPE,
            )
            .decode()
            .strip()
        )
        return result

    def wait_healthy(self, service):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            container = (
                self.command(
                    self.compose + ["ps", "-q", service], stdout=subprocess.PIPE
                )
                .decode()
                .strip()
            )
            if container:
                status = (
                    self.command(
                        [
                            "docker",
                            "inspect",
                            "--format",
                            "{{.State.Health.Status}}",
                            container,
                        ],
                        stdout=subprocess.PIPE,
                    )
                    .decode()
                    .strip()
                )
                if status == "healthy":
                    return
            time.sleep(2)
        raise TimeoutError("Dependency did not recover before the deadline")

    def backup_restore(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        database = (
            self.command(
                self.compose + ["exec", "-T", "postgres", "printenv", "POSTGRES_DB"],
                stdout=subprocess.PIPE,
            )
            .decode()
            .strip()
        )
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", database):
            raise ValueError("Unexpected source database name")
        target = "recovery_" + uuid4().hex
        archive = directory / f"{target}.dump"
        created = False
        started = time.monotonic()
        try:
            self.service("stop", "api")
            self.service("stop", "worker")
            expected = self.fingerprint(database)
            with archive.open("xb") as output:
                self.pg(
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--dbname",
                    database,
                    stdout=output,
                )
            if self.fingerprint(database) != expected:
                raise RuntimeError(
                    "Source changed during backup; quiesce writers and rerun"
                )
            self.pg("createdb", target, stdout=subprocess.PIPE)
            created = True
            with archive.open("rb") as source:
                self.pg(
                    "pg_restore",
                    "--exit-on-error",
                    "--single-transaction",
                    "--no-owner",
                    "--no-acl",
                    "--dbname",
                    target,
                    stdin=source,
                    stdout=subprocess.PIPE,
                )
            actual = self.fingerprint(target)
            if expected != actual:
                raise AssertionError("Restore row or index fingerprints differ")
            return {
                "verified": True,
                "tables": len(TABLES),
                "seconds": time.monotonic() - started,
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "archive_bytes": archive.stat().st_size,
            }
        finally:
            try:
                if created:
                    self.pg("dropdb", target, stdout=subprocess.PIPE)
            finally:
                try:
                    self.service("start", "api")
                finally:
                    self.service("start", "worker")


def await_events(engine, events, timeout=90):
    from sqlalchemy.exc import SQLAlchemyError

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            scored, _, processed = pipeline_snapshot(engine, events)
            if len(processed) == len(events) and len(scored) == len(events):
                return
        except SQLAlchemyError:
            pass
        time.sleep(0.5)
    raise TimeoutError("Events did not persist after dependency recovery")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--group", default="transaction-processor-v1")
    parser.add_argument("--output", default=".local/recovery-drill")
    args = parser.parse_args()
    drill = Drill(args.project)
    drill.validate_ports()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", args.group):
        parser.error("Invalid consumer group")
    import random

    from app.core.config import Settings
    from generate_transactions import generate_event
    from sqlalchemy import create_engine

    database = (
        drill.command(
            drill.compose + ["exec", "-T", "postgres", "printenv", "POSTGRES_DB"],
            stdout=subprocess.PIPE,
        )
        .decode()
        .strip()
    )
    settings = Settings(
        database_url=None,
        postgres_host="127.0.0.1",
        postgres_port=5432,
        postgres_db=database,
    )
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        hide_parameters=True,
        connect_args={"connect_timeout": 3},
    )
    events = [generate_event(random.Random(i)) for i in range(10)]
    result = {"recorded_at": datetime.now(UTC).isoformat(), "project": args.project}
    publish(events, "127.0.0.1:9092")
    await_events(engine, events)
    before = drill.fingerprint(database)
    expected_replay = int(before["processed_events"].split("|", 1)[0])
    try:
        drill.service("stop", "worker")
        drill.command(
            drill.compose
            + [
                "exec",
                "-T",
                "kafka",
                "/opt/kafka/bin/kafka-consumer-groups.sh",
                "--bootstrap-server",
                "kafka:29092",
                "--group",
                args.group,
                "--topic",
                "transactions.v1",
                "--reset-offsets",
                "--to-earliest",
                "--execute",
            ],
            stdout=subprocess.PIPE,
        )
    finally:
        drill.service("start", "worker")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        metrics = worker_snapshot()
        if (
            metrics.get("duplicates", 0) >= expected_replay
            and metrics.get("lag") == 0
            and metrics.get("known_partitions", 0) > 0
            and metrics.get("statistics_age_seconds", 999) < 60
        ):
            break
        time.sleep(1)
    else:
        raise TimeoutError("Offset replay was not observed to completion")
    if before != drill.fingerprint(database):
        raise AssertionError("Offset replay changed persisted row fingerprints")
    result["offset_replay"] = {
        "verified": True,
        "minimum_duplicate_events": expected_replay,
        "final_lag": metrics["lag"],
        "known_partitions": metrics["known_partitions"],
    }
    for service in ("kafka", "postgres"):
        new_events = [generate_event(random.Random(i)) for i in range(3)]
        started = time.monotonic()
        try:
            drill.service("stop", service)
            if service == "postgres":
                publish(new_events, "127.0.0.1:9092")
            time.sleep(3)
        finally:
            drill.service("start", service)
        drill.wait_healthy(service)
        if service == "kafka":
            publish(new_events, "127.0.0.1:9092")
        await_events(engine, new_events)
        result[service + "_recovery"] = {
            "verified": True,
            "persisted_events": len(new_events),
            "seconds": time.monotonic() - started,
        }
    result["backup_restore"] = drill.backup_restore(args.output)
    save_report(Path(args.output) / "report.json", result)
    print(json.dumps(result, indent=2))
    engine.dispose()


if __name__ == "__main__":
    main()
