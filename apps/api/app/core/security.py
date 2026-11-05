"""Per-user opaque bearer credentials; no shared/default login or caller-chosen role."""

import hashlib
import hmac
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

from app.core.config import Settings

bearer = HTTPBearer(auto_error=False)
LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return {count, redis.call('TTL', KEYS[1])}
"""


class Principal(BaseModel):
    username: str
    role: str


@lru_cache
def security_settings():
    return Settings()


class RateLimiter:
    def __init__(self, settings):
        self.settings = settings
        self.redis = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=settings.redis_timeout_seconds,
            socket_timeout=settings.redis_timeout_seconds,
            retry_on_timeout=False,
            retry=Retry(NoBackoff(), 0),
        )

    def check(self, identity: str, multiplier: int = 1):
        key = "security:rate:v1:" + hashlib.sha256(identity.encode()).hexdigest()
        try:
            count, ttl = self.redis.eval(
                LIMIT_SCRIPT, 1, key, self.settings.rate_limit_window_seconds
            )
        except RedisError:
            raise HTTPException(
                503, "Request protection is temporarily unavailable", headers={"Retry-After": "5"}
            ) from None
        if count > self.settings.rate_limit_requests * multiplier:
            raise HTTPException(
                429, "Rate limit exceeded", headers={"Retry-After": str(max(ttl, 1))}
            )


@lru_cache
def get_rate_limiter():
    return RateLimiter(security_settings())


def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(security_settings)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> Principal:
    # IP budget covers invalid tokens too. Forwarded headers are not trusted here.
    limiter.check("ip:" + (request.client.host if request.client else "unknown"), multiplier=5)
    if credentials is None or not 32 <= len(credentials.credentials) <= 256:
        raise HTTPException(
            401, "Valid bearer authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    user = None
    for candidate in settings.auth_users:
        if hmac.compare_digest(candidate.token_sha256, digest):
            user = candidate
    if user is None:
        raise HTTPException(
            401, "Valid bearer authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    limiter.check("user:" + user.username)
    return Principal(username=user.username, role=user.role)


Authenticated = Annotated[Principal, Depends(get_principal)]


def require_administrator(principal: Authenticated):
    if principal.role != "administrator":
        raise HTTPException(403, "Administrator role required")
    return principal
