"""
Redis 缓存连接管理

提供 Redis 连接池和工厂函数
"""

import redis
from functools import lru_cache

from app.config import get_settings


@lru_cache()
def get_redis() -> redis.Redis:
    """获取 Redis 连接（带缓存，复用连接池）"""
    settings = get_settings()
    pool = redis.ConnectionPool.from_url(
        settings.redis.REDIS_URL,
        max_connections=20,
        socket_timeout=5,
        socket_connect_timeout=5,
        retry_on_timeout=True,
    )
    return redis.Redis(connection_pool=pool)
