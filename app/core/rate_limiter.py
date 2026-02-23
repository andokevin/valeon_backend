# app/core/rate_limiter.py (MODIFIÉ)
import time
from typing import Dict, Tuple
from fastapi import HTTPException, Request
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self):
        self.enabled = settings.RATE_LIMIT_ENABLED
        self.limit = settings.RATE_LIMIT_REQUESTS
        self.window = settings.RATE_LIMIT_PERIOD
        self.requests: Dict[str, list] = {}
        self._cleanup_counter = 0

    def check(self, request: Request) -> None:
        if not self.enabled:
            return
        
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        cutoff = now - self.window
        
        # Nettoyage périodique
        self._cleanup_counter += 1
        if self._cleanup_counter > 1000:
            self._cleanup_old_requests(cutoff)
            self._cleanup_counter = 0
        
        # Initialiser si nécessaire
        if ip not in self.requests:
            self.requests[ip] = []
        
        # Filtrer les requêtes anciennes
        self.requests[ip] = [t for t in self.requests[ip] if t > cutoff]
        
        # Vérifier la limite
        if len(self.requests[ip]) >= self.limit:
            logger.warning(f"Rate limit exceeded for IP {ip}: {len(self.requests[ip])}/{self.limit}")
            raise HTTPException(
                status_code=429, 
                detail={
                    "error": "Trop de requêtes",
                    "message": f"Limite de {self.limit} requêtes par {self.window} secondes atteinte",
                    "retry_after": int(self.window - (now - self.requests[ip][0])),
                    "limit": self.limit,
                    "window": self.window
                }
            )
        
        # Ajouter la requête actuelle
        self.requests[ip].append(now)

    def _cleanup_old_requests(self, cutoff: float):
        """Nettoie les anciennes requêtes de toutes les IPs."""
        for ip in list(self.requests.keys()):
            self.requests[ip] = [t for t in self.requests[ip] if t > cutoff]
            if not self.requests[ip]:
                del self.requests[ip]
        
        logger.debug(f"Rate limiter cleanup: {len(self.requests)} IPs remaining")

    def remaining(self, request: Request) -> Tuple[int, int]:
        if not self.enabled:
            return self.limit, 0
        
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        cutoff = now - self.window
        
        valid = [t for t in self.requests.get(ip, []) if t > cutoff]
        remaining = max(0, self.limit - len(valid))
        reset = int(self.window - (now - valid[0])) if valid else 0
        
        return remaining, reset
    
    def get_usage(self, request: Request) -> Dict:
        """Retourne les statistiques d'utilisation pour le client."""
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        cutoff = now - self.window
        
        valid = [t for t in self.requests.get(ip, []) if t > cutoff]
        
        return {
            "used": len(valid),
            "limit": self.limit,
            "remaining": max(0, self.limit - len(valid)),
            "reset_in": int(self.window - (now - valid[0])) if valid else 0,
            "window_seconds": self.window
        }

rate_limiter = RateLimiter()