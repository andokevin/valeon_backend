# app/core/rate_limiter.py
import time
from typing import Dict, Tuple
from fastapi import HTTPException, Request
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """
    Rate limiter simple en mémoire.
    Pour la production, utiliser Redis.
    """
    
    def __init__(self):
        self.enabled = settings.RATE_LIMIT_ENABLED
        self.requests_per_minute = settings.RATE_LIMIT_REQUESTS
        self.window_size = settings.RATE_LIMIT_PERIOD  # secondes
        
        # Stockage: {ip: [(timestamp, count), ...]}
        self.requests: Dict[str, list] = {}
    
    def check_rate_limit(self, request: Request) -> None:
        """Vérifie si la requête dépasse la limite."""
        if not self.enabled:
            return
        
        # Récupérer l'IP du client
        client_ip = request.client.host if request.client else "unknown"
        
        now = time.time()
        window_start = now - self.window_size
        
        # Nettoyer les anciennes entrées
        if client_ip in self.requests:
            self.requests[client_ip] = [
                ts for ts in self.requests[client_ip]
                if ts > window_start
            ]
        else:
            self.requests[client_ip] = []
        
        # Compter les requêtes dans la fenêtre
        request_count = len(self.requests[client_ip])
        
        if request_count >= self.requests_per_minute:
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            raise HTTPException(
                status_code=429,
                detail="Trop de requêtes. Veuillez réessayer plus tard."
            )
        
        # Ajouter la requête courante
        self.requests[client_ip].append(now)
    
    def get_remaining(self, request: Request) -> Tuple[int, int]:
        """Retourne le nombre de requêtes restantes et le temps de reset."""
        if not self.enabled:
            return self.requests_per_minute, 0
        
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self.window_size
        
        if client_ip in self.requests:
            valid_requests = [ts for ts in self.requests[client_ip] if ts > window_start]
            count = len(valid_requests)
            oldest = min(valid_requests) if valid_requests else now
            reset_time = int(self.window_size - (now - oldest)) if valid_requests else 0
        else:
            count = 0
            reset_time = 0
        
        remaining = max(0, self.requests_per_minute - count)
        return remaining, reset_time

rate_limiter = RateLimiter()