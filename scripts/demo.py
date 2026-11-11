"""Start, verify, and stop the disposable event-to-alert demonstration stack."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / ".local/demo"
STATE = DEMO / "state.json"
TOKEN = DEMO / "operator.token"
CONTEXT = DEMO / "e2e-context.json"
FAILURE_LOG = DEMO / "failure.log"


def run(
    command: list[str], *, env: dict[str, str] | None = None, capture: bool = False
) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def load_state() -> dict:
    if not STATE.exists():
        raise RuntimeError("No active demo. Run: python scripts/demo.py start")
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if not re.fullmatch(r"demo-v1-[0-9]{8}[0-9]{6}", state.get("project", "")):
        raise RuntimeError("Refusing an invalid demo project name")
    return state


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def start() -> None:
    if STATE.exists():
        raise RuntimeError("A demo is already active; verify or stop it first")
    if shutil.which("docker") is None:
        raise RuntimeError("Docker is required for the demonstration")
    DEMO.mkdir(parents=True, exist_ok=True)
    project = f"demo-v1-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    identity = run(
        [
            sys.executable,
            "scripts/create_auth_user.py",
            "--username",
            "demo-operator",
            "--role",
            "operator",
            "--token-file",
            str(TOKEN),
        ],
        capture=True,
    )
    ports = {
        "api": free_port(),
        "web": free_port(),
        "postgres": free_port(),
        "redis": free_port(),
        "kafka": free_port(),
        "worker_metrics": free_port(),
    }
    state = {
        "schema_version": 1,
        "project": project,
        "created_at": datetime.now(UTC).isoformat(),
        "ports": ports,
    }
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["AUTH_USERS"] = json.dumps([json.loads(identity)])
    environment.update(
        {
            "API_PORT": str(ports["api"]),
            "WEB_PORT": str(ports["web"]),
            "POSTGRES_PORT": str(ports["postgres"]),
            "REDIS_PORT": str(ports["redis"]),
            "KAFKA_PORT": str(ports["kafka"]),
            "WORKER_METRICS_PORT": str(ports["worker_metrics"]),
        }
    )
    try:
        run(
            [
                "docker",
                "compose",
                "-p",
                project,
                "up",
                "--build",
                "-d",
                "--wait",
                "api",
                "worker",
                "web",
            ],
            env=environment,
        )
        api_url = f"http://127.0.0.1:{ports['api']}"
        web_url = f"http://127.0.0.1:{ports['web']}"
        run(
            [
                sys.executable,
                "scripts/smoke_test.py",
                "--api-url",
                api_url,
                "--web-url",
                web_url,
            ]
        )
        run(
            [
                sys.executable,
                "scripts/check_contracts.py",
                "--url",
                f"{api_url}/openapi.json",
            ]
        )
        run(
            [
                sys.executable,
                "scripts/run_end_to_end.py",
                "prepare",
                "--token-file",
                str(TOKEN),
                "--context",
                str(CONTEXT),
                "--api-url",
                api_url,
                "--bootstrap-servers",
                f"127.0.0.1:{ports['kafka']}",
            ]
        )
    except Exception:
        logs = subprocess.run(
            ["docker", "compose", "-p", project, "logs", "--no-color"],
            cwd=ROOT,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        FAILURE_LOG.write_text(logs.stdout, encoding="utf-8")
        subprocess.run(
            ["docker", "compose", "-p", project, "down", "-v"],
            cwd=ROOT,
            check=False,
        )
        for path in (CONTEXT, TOKEN, STATE):
            path.unlink(missing_ok=True)
        print(f"Demo failed; sanitized service logs saved to {FAILURE_LOG}")
        raise
    context = json.loads(CONTEXT.read_text(encoding="utf-8"))
    print(f"Demo ready: http://127.0.0.1:{ports['web']}")
    print(f"Token file: {TOKEN}")
    print(f"Transaction: {context['transaction_id']}")
    print(f"Alert: {context['alert_id']}")
    print(
        "Sign in, inspect the transaction and alert evidence, then resolve the alert."
    )
    print("Verify with: python scripts/demo.py verify")


def verify() -> None:
    state = load_state()
    run(
        [
            sys.executable,
            "scripts/run_end_to_end.py",
            "verify",
            "--context",
            str(CONTEXT),
            "--api-url",
            f"http://127.0.0.1:{state['ports']['api']}",
        ]
    )
    print(
        "PASS: event ingestion, scoring, alert display, resolution, and audit history"
    )


def stop() -> None:
    state = load_state()
    run(["docker", "compose", "-p", state["project"], "down", "-v"])
    for path in (CONTEXT, TOKEN, STATE, FAILURE_LOG):
        path.unlink(missing_ok=True)
    print(f"Removed disposable demo project {state['project']} and its volumes")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "verify", "stop"))
    args = parser.parse_args()
    {"start": start, "verify": verify, "stop": stop}[args.command]()


if __name__ == "__main__":
    main()
