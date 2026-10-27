import time
from typing import Tuple, Dict
from fastapi import Request, HTTPException, status
from backend.core.cache import cache_manager
from backend.core.logging import get_logger

logger = get_logger("ThothRateLimiter")

# Local in-memory token bucket state for fail-open resilience
_LOCAL_BUCKETS: Dict[str, Dict[str, float]] = {}

class TokenBucketRateLimiter:
    def __init__(self, capacity: int = 60, refill_rate_per_sec: float = 1.0):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate_per_sec)

    async def acquire(self, key: str, tokens: int = 1) -> Tuple[bool, float]:
        now = time.time()
        client = await cache_manager.get_client()

        if client:
            try:
                bucket_key = f"thoth:ratelimit:bucket:{key}"
                pipe = client.pipeline()
                pipe.hget(bucket_key, "tokens")
                pipe.hget(bucket_key, "last_updated")
                res = await pipe.execute()

                current_tokens = float(res[0]) if res[0] else self.capacity
                last_updated = float(res[1]) if res[1] else now

                elapsed = now - last_updated
                current_tokens = min(self.capacity, current_tokens + (elapsed * self.refill_rate))

                if current_tokens >= tokens:
                    current_tokens -= tokens
                    await client.hset(bucket_key, mapping={
                        "tokens": str(current_tokens),
                        "last_updated": str(now)
                    })
                    await client.expire(bucket_key, 120)
                    return True, 0.0
                else:
                    wait_time = (tokens - current_tokens) / self.refill_rate
                    return False, wait_time
            except Exception as e:
                logger.warning(f"Redis rate-limit query failed: {e}. Falling back to memory.")

        # Local in-memory fallback
        state = _LOCAL_BUCKETS.setdefault(key, {"tokens": self.capacity, "last_updated": now})
        elapsed = now - state["last_updated"]
        state["tokens"] = min(self.capacity, state["tokens"] + (elapsed * self.refill_rate))
        state["last_updated"] = now

        if state["tokens"] >= tokens:
            state["tokens"] -= tokens
            return True, 0.0
        else:
            wait_time = (tokens - state["tokens"]) / self.refill_rate
            return False, wait_time

async def rate_limit_gate(request: Request, key_prefix: str = "ip", capacity: int = 60, refill: float = 1.0) -> None:
    client_host = request.client.host if request.client else "127.0.0.1"
    limiter = TokenBucketRateLimiter(capacity=capacity, refill_rate_per_sec=refill)
    allowed, wait_sec = await limiter.acquire(f"{key_prefix}:{client_host}")
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Please wait {wait_sec:.1f} seconds."
        )
