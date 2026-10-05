import time
from collections import defaultdict
from typing import Dict, List

class SlidingWindowRateLimiter:
    def __init__(self, limit: int = 10, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self.last_cleanup = time.time()

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        self._periodic_cleanup(now)

        timestamps = self.requests[key]
        # Keep only timestamps in the current window
        cutoff = now - self.window_seconds
        valid_timestamps = [t for t in timestamps if t > cutoff]
        self.requests[key] = valid_timestamps

        if len(valid_timestamps) >= self.limit:
            return False

        self.requests[key].append(now)
        return True

    def _periodic_cleanup(self, now: float) -> None:
        # Run cleanup every 5 minutes to prevent memory leaks from inactive keys
        if now - self.last_cleanup > 300:
            cutoff = now - self.window_seconds
            keys_to_delete = [
                k for k, v in self.requests.items()
                if not v or v[-1] <= cutoff
            ]
            for k in keys_to_delete:
                del self.requests[k]
            self.last_cleanup = now

# Global instance for generation endpoints
generation_rate_limiter = SlidingWindowRateLimiter(limit=10, window_seconds=60)
# Global instance for general read endpoints
general_rate_limiter = SlidingWindowRateLimiter(limit=60, window_seconds=60)
