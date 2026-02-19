# app/core/cache.py
import redis
import json
from typing import Optional, Any, Callable
from functools import wraps
import hashlib
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class CacheManager:
    """
    Gestionnaire de cache Redis.
    """
    
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
                    socket_timeout=2
                )
                # Test de connexion
                self.redis_client.ping()
                logger.info("✅ Cache Redis connecté")
            except Exception as e:
                logger.warning(f"⚠️ Cache Redis non disponible: {e}")
                self.enabled = False
                self.redis_client = None
    
    def get(self, key: str) -> Optional[Any]:
        """Récupère une valeur du cache."""
        if not self.enabled or not self.redis_client:
            return None
        
        try:
            value = self.redis_client.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            logger.error(f"Erreur cache get {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Stocke une valeur dans le cache."""
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            ttl = ttl or self.ttl
            self.redis_client.setex(key, ttl, json.dumps(value, default=str))
            return True
        except Exception as e:
            logger.error(f"Erreur cache set {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Supprime une valeur du cache."""
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Erreur cache delete {key}: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """Supprime toutes les clés correspondant à un pattern."""
        if not self.enabled or not self.redis_client:
            return 0
        
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Erreur cache clear pattern {pattern}: {e}")
            return 0
    
    def cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Génère une clé de cache unique."""
        key_parts = [prefix]
        key_parts.extend(str(arg) for arg in args)
        if kwargs:
            key_parts.append(hashlib.md5(str(sorted(kwargs.items())).encode()).hexdigest()[:8])
        return ":".join(key_parts)
    
    def cached(self, ttl: Optional[int] = None):
        """
        Décorateur pour mettre en cache le résultat d'une fonction.
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                if not self.enabled:
                    return await func(*args, **kwargs)
                
                # Générer une clé unique
                key = self.cache_key(func.__name__, *args, **kwargs)
                
                # Vérifier le cache
                cached_value = self.get(key)
                if cached_value is not None:
                    logger.debug(f"Cache hit: {key}")
                    return cached_value
                
                # Exécuter la fonction
                result = await func(*args, **kwargs)
                
                # Mettre en cache
                self.set(key, result, ttl)
                logger.debug(f"Cache set: {key}")
                
                return result
            return wrapper
        return decorator

# Instance globale
cache = CacheManager()