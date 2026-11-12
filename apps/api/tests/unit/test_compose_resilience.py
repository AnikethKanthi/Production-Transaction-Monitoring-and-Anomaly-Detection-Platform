import re
from pathlib import Path


COMPOSE_FILE = Path(__file__).resolve().parents[4] / "docker-compose.yml"
LONG_RUNNING_SERVICES = {
    "api",
    "grafana",
    "kafka",
    "postgres",
    "prometheus",
    "redis",
    "web",
    "worker",
}
ONE_SHOT_SERVICES = {"kafka-init", "migrate"}


def _restart_policies() -> dict[str, str]:
    policies: dict[str, str] = {}
    current_service: str | None = None
    in_services = False

    for line in COMPOSE_FILE.read_text(encoding="utf-8").splitlines():
        if line == "services:":
            in_services = True
            continue
        if in_services and line and not line.startswith(" "):
            break

        service_match = re.fullmatch(r"  ([a-z0-9-]+):", line)
        if service_match:
            current_service = service_match.group(1)
            continue

        policy_match = re.fullmatch(r"    restart:\s*(\S+)", line)
        if current_service and policy_match:
            policies[current_service] = policy_match.group(1)

    return policies


def test_long_running_services_recover_after_container_engine_restart() -> None:
    policies = _restart_policies()

    assert {service: policies.get(service) for service in LONG_RUNNING_SERVICES} == {
        service: "unless-stopped" for service in LONG_RUNNING_SERVICES
    }


def test_one_shot_services_are_not_restarted() -> None:
    policies = _restart_policies()

    assert ONE_SHOT_SERVICES.isdisjoint(policies)
