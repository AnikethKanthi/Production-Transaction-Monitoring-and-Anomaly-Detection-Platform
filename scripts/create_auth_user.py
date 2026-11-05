"""Generate a per-user token into a private file and print only its server hash entry."""

import argparse
import hashlib
import json
import os
import re
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", required=True, choices=["operator", "administrator"])
    parser.add_argument("--token-file", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", args.username):
        parser.error(
            "Username must contain 1–128 letters, digits, dots, underscores or hyphens"
        )
    token = secrets.token_urlsafe(32)
    args.token_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            args.token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
    except FileExistsError:
        parser.error(
            "Token file already exists; use a new path to avoid overwriting credentials"
        )
    with os.fdopen(descriptor, "w") as output:
        output.write(token + "\n")
    print(
        json.dumps(
            {
                "username": args.username,
                "role": args.role,
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
