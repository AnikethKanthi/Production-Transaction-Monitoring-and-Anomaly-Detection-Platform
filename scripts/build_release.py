"""Build and record the three immutable application images for a release."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {
    "api": (ROOT / "apps/api", ROOT / "apps/api/Dockerfile"),
    "worker": (ROOT, ROOT / "apps/worker/Dockerfile"),
    "web": (ROOT / "apps/web", ROOT / "apps/web/Dockerfile"),
}


def run(command: list[str]) -> str:
    result = subprocess.run(
        command, cwd=ROOT, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-url", default="local")
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".local/release/manifest.json"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version):
        parser.error("--version must be a semantic version such as 1.0.0")
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if args.version != expected:
        parser.error(f"--version must match VERSION ({expected})")
    if shutil.which("docker") is None:
        parser.error("Docker is required to build release images")
    revision = run(["git", "rev-parse", "HEAD"])
    records = []
    for component, (context, dockerfile) in IMAGES.items():
        tag = f"transaction-monitoring-{component}:{args.version}"
        run(
            [
                "docker",
                "build",
                "--file",
                str(dockerfile),
                "--build-arg",
                f"VERSION={args.version}",
                "--build-arg",
                f"REVISION={revision}",
                "--build-arg",
                f"SOURCE_URL={args.source_url}",
                "--tag",
                tag,
                str(context),
            ]
        )
        inspection = json.loads(run(["docker", "image", "inspect", tag]))[0]
        records.append(
            {
                "component": component,
                "tag": tag,
                "image_id": inspection["Id"],
                "repo_digests": inspection.get("RepoDigests", []),
            }
        )
    manifest = {
        "schema_version": 1,
        "version": args.version,
        "revision": revision,
        "source_url": args.source_url,
        "built_at": datetime.now(UTC).isoformat(),
        "images": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "version": args.version,
                "images": len(records),
                "manifest": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
