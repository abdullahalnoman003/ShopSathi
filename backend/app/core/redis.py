import redis

from app.core.config import get_settings


def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
