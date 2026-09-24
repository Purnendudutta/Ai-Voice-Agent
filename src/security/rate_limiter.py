"""
Sliding-Window Token Bucket Rate Limiter
"""

import time
import asyncio
from typing import Dict


class RateLimiter:
    """Threadsafe token-bucket rate limiter for IPC and tool invocations."""

    def __init__(self, capacity: int = 60, refill_rate_per_sec: float = 1.0):
        self.capacity = float(capacity)
        self.refill_rate = refill_rate_per_sec
        self.tokens: Dict[str, float] = {}
        self.last_update: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, client_id: str = "default", cost: float = 1.0) -> bool:
        """Attempts to consume tokens. Returns True if permitted, False otherwise."""
        async with self._lock:
            now = time.time()
            if client_id not in self.tokens:
                self.tokens[client_id] = self.capacity
                self.last_update[client_id] = now

            # Refill tokens based on elapsed time
            elapsed = now - self.last_update[client_id]
            self.tokens[client_id] = min(
                self.capacity,
                self.tokens[client_id] + elapsed * self.refill_rate
            )
            self.last_update[client_id] = now

            if self.tokens[client_id] >= cost:
                self.tokens[client_id] -= cost
                return True
            return False

    async def reset(self, client_id: str = "default") -> None:
        async with self._lock:
            self.tokens[client_id] = self.capacity
            self.last_update[client_id] = time.time()


global_rate_limiter = RateLimiter(capacity=60, refill_rate_per_sec=1.0)
