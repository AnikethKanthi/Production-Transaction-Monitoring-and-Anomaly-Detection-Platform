"""Defense in depth for log strings; request bodies and exception text are never logged."""

import os
import re

PAN = re.compile(r"(?<![A-Za-z0-9_-])(?:\d[ -]?){12,18}\d(?![A-Za-z0-9_-])")
SECRET = re.compile(
    r"(?i)([\"']?(?:password|passwd|secret|token|api[_-]?key|authorization|cvv|cvc|pan|card[_-]?number)[\"']?\s*[:=]\s*)"
    r"(?:[\"'][^\"']*[\"']|[^\s,;}]+)"
)
BEARER = re.compile(r"(?i)\bBearer\s+[^\s\"',;]+")
USERINFO = re.compile(r"(\w+://)[^\s/@]+:[^\s/@]+@")
SENSITIVE_KEY = re.compile(
    r"(?i)^(password|passwd|secret|token|api[_-]?key|authorization|cvv|cvc|pan|card[_-]?number)$"
)


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if SENSITIVE_KEY.match(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    value = BEARER.sub("Bearer [REDACTED]", value)
    value = SECRET.sub(r"\1[REDACTED]", value)
    value = USERINFO.sub(r"\1[REDACTED]@", value)
    value = PAN.sub("[REDACTED_CARD]", value)
    for name, secret in os.environ.items():
        if any(word in name.upper() for word in ("PASSWORD", "SECRET", "TOKEN", "API_KEY")):
            if len(secret) >= 4:
                value = value.replace(secret, "[REDACTED]")
    return value
