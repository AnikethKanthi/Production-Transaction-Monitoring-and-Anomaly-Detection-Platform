"""Validate version alignment, exact direct pins, release docs, and event schemas."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from itertools import chain
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-tag", action="store_true")
    args = parser.parse_args()
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise RuntimeError("VERSION is not semantic")
    for project in ("api", "worker"):
        data = tomllib.loads(
            (ROOT / f"apps/{project}/pyproject.toml").read_text(encoding="utf-8")
        )
        if data["project"]["version"] != version:
            raise RuntimeError(f"{project} version does not match VERSION")
        if any("==" not in item for item in data["build-system"]["requires"]):
            raise RuntimeError(f"{project} has an unpinned build dependency")
        dependencies = data["project"]["dependencies"]
        optional = list(
            chain.from_iterable(
                data["project"].get("optional-dependencies", {}).values()
            )
        )
        if any("==" not in item for item in dependencies + optional):
            raise RuntimeError(f"{project} has an unpinned direct dependency")
    package = json.loads((ROOT / "apps/web/package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "apps/web/package-lock.json").read_text(encoding="utf-8"))
    if package["version"] != version or lock["version"] != version:
        raise RuntimeError("web package versions do not match VERSION")
    specs = package["dependencies"] | package["devDependencies"]
    if any(
        not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value) for value in specs.values()
    ):
        raise RuntimeError("web has an unpinned direct dependency")
    for path in (ROOT / "contracts/events").glob("*.schema.json"):
        json.loads(path.read_text(encoding="utf-8"))
    required_docs = [
        "README.md",
        "docs/api/endpoints.md",
        "docs/architecture/overview.md",
        "docs/architecture/data-model.md",
        "docs/kafka-events.md",
        "docs/runbooks/deployment.md",
        "docs/runbooks/operator-investigation.md",
        "docs/runbooks/incident-response.md",
        "docs/runbooks/model-rollback.md",
    ]
    for relative in required_docs:
        if len((ROOT / relative).read_text(encoding="utf-8").strip()) < 100:
            raise RuntimeError(f"release document is incomplete: {relative}")
    if args.require_tag:
        tag_commit = subprocess.run(
            ["git", "rev-list", "-n", "1", f"v{version}"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        if tag_commit != head:
            raise RuntimeError(f"v{version} does not point at HEAD")
    print(f"PASS release {version}: versions, pins, schemas, and documentation")


if __name__ == "__main__":
    main()
