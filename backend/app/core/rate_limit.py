from fastapi import HTTPException, status

from app.core.redis import get_redis


def check_rate_limit(scope: str, key: str, limit: int, window_seconds: int) -> None:
    """Fixed-window counter in Redis; raises 429 when the limit is exceeded."""
    redis_key = f"rl:{scope}:{key}"
    r = get_redis()
    count = r.incr(redis_key)
    if count == 1:
        r.expire(redis_key, window_seconds)
    if count > limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Please try again later."
        )
