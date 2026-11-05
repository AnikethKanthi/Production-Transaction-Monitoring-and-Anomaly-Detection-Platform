import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.security import RateLimiter

pytestmark = pytest.mark.integration


def test_atomic_distributed_limit_and_expiration():
    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        pytest.skip("Set TEST_REDIS_URL to run Redis integration tests")
    limiter = RateLimiter(Settings(_env_file=None, redis_url=url, rate_limit_requests=5))
    identity = "test:" + uuid4().hex
    key = "security:rate:v1:" + hashlib.sha256(identity.encode()).hexdigest()

    def attempt(_):
        try:
            limiter.check(identity)
            return 200
        except HTTPException as error:
            return error.status_code

    try:
        with ThreadPoolExecutor(max_workers=10) as pool:
            outcomes = list(pool.map(attempt, range(10)))
        assert outcomes.count(200) == 5 and outcomes.count(429) == 5
        assert 0 < limiter.redis.ttl(key) <= 60
        limiter.redis.expire(key, 0)
        limiter.check(identity)
        assert int(limiter.redis.get(key)) == 1
    finally:
        limiter.redis.delete(key)
        limiter.redis.close()
