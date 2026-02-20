import redis
import json
from typing import Optional, Any
import hashlib
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self):
        self.redis_client = None
        self.enabled = settings.REDIS_ENABLED
        self.ttl = settings.CACHE_TTL_SECONDS
        if self.enabled:
            try:
                self.redis_client = redis.Redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                self.redis_client.ping()
                logger.info("Cache Redis connecté")
            except Exception as e:
                logger.warning(f"Cache Redis non disponible: {e}")
                self.enabled = False
                self.redis_client = None

    def get(self, key: str) -> Optional[Any]:
        if not self.enabled or not self.redis_client:
            return None
        try:
            value = self.redis_client.get(key)
            return json.loads(value) if value else None
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        if not self.enabled or not self.redis_client:
            return False
        try:
            self.redis_client.setex(key, ttl or self.ttl, json.dumps(value, default=str))
            return True
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        if not self.enabled or not self.redis_client:
            return False
        try:
            self.redis_client.delete(key)
            return True
        except Exception:
            return False

    def clear_pattern(self, pattern: str) -> int:
        if not self.enabled or not self.redis_client:
            return 0
        try:
            keys = self.redis_client.keys(pattern)
            return self.redis_client.delete(*keys) if keys else 0
        except Exception:
            return 0

cache = CacheManager()
