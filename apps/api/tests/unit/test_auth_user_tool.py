import hashlib
import json
import subprocess
import sys
from pathlib import Path


def test_credential_generator_saves_secret_but_prints_only_hash_and_refuses_overwrite(tmp_path):
    script = Path(__file__).resolve().parents[4] / "scripts/create_auth_user.py"
    path = tmp_path / "operator.token"
    command = [
        sys.executable,
        str(script),
        "--username",
        "operator-1",
        "--role",
        "operator",
        "--token-file",
        str(path),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=True)
    token = path.read_text().strip()
    assert len(token) >= 32 and token not in first.stdout + first.stderr
    assert json.loads(first.stdout) == {
        "username": "operator-1",
        "role": "operator",
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    }
    second = subprocess.run(command, capture_output=True, text=True)
    assert second.returncode != 0
    assert path.read_text().strip() == token
    assert token not in second.stdout + second.stderr
