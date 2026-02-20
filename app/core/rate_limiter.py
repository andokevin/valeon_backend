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

    def check(self, request: Request) -> None:
        if not self.enabled:
            return
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        cutoff = now - self.window
        self.requests.setdefault(ip, [])
        self.requests[ip] = [t for t in self.requests[ip] if t > cutoff]
        if len(self.requests[ip]) >= self.limit:
            raise HTTPException(status_code=429, detail="Trop de requêtes. Réessayez plus tard.")
        self.requests[ip].append(now)
        if len(self.requests) > 50_000:
            self.requests.clear()

    def remaining(self, request: Request) -> Tuple[int, int]:
        if not self.enabled:
            return self.limit, 0
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        cutoff = now - self.window
        valid = [t for t in self.requests.get(ip, []) if t > cutoff]
        remaining = max(0, self.limit - len(valid))
        reset = int(self.window - (now - min(valid))) if valid else 0
        return remaining, reset

rate_limiter = RateLimiter()
