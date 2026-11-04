"""Validate provisioned dashboard sources and every panel's PromQL with promtool."""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--promtool", default="promtool")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "observability"
    datasource = json.loads(
        (root / "grafana/provisioning/datasources/prometheus.yml").read_text()
    )["datasources"][0]
    assert datasource["uid"] == "prometheus"
    assert datasource["url"] == "http://prometheus:9090"
    provider = json.loads(
        (root / "grafana/provisioning/dashboards/default.yml").read_text()
    )["providers"][0]
    assert provider["options"]["path"] == "/var/lib/grafana/dashboards"
    dashboards = list((root / "grafana/dashboards").glob("*.json"))
    assert len(dashboards) == 3
    uids, rules = set(), []
    for path in dashboards:
        dashboard = json.loads(path.read_text())
        assert dashboard["uid"] not in uids
        uids.add(dashboard["uid"])
        assert dashboard["panels"]
        for panel in dashboard["panels"]:
            assert panel["datasource"]["uid"] == datasource["uid"]
            for target in panel["targets"]:
                rules.append(
                    {"record": f"dashboard_query_{len(rules)}", "expr": target["expr"]}
                )
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "panels.json"
        path.write_text(json.dumps({"groups": [{"name": "panels", "rules": rules}]}))
        subprocess.run([args.promtool, "check", "rules", str(path)], check=True)
    print(f"Validated {len(dashboards)} dashboards and {len(rules)} panel expressions.")


if __name__ == "__main__":
    main()
