import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from scripts.check_contracts import REQUIRED_OPERATIONS, validate  # noqa: E402

from app.main import app  # noqa: E402


def test_deployed_web_contract_is_present_in_openapi() -> None:
    document = app.openapi()

    validate(document)

    assert len(REQUIRED_OPERATIONS) == 11
