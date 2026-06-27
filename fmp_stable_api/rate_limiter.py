import threading
import time
from datetime import datetime, timedelta


class RateLimiter:
    """Sliding-window rate limiter that resets at the top of each minute."""

    def __init__(self, minute_limit: int):
        self.minute_limit = minute_limit
        self._requests_made = 0
        self._window_start = self._current_minute()
        self._lock = threading.Lock()

    def _current_minute(self) -> datetime:
        now = datetime.now()
        return now.replace(second=0, microsecond=0)

    def _maybe_reset(self):
        current = self._current_minute()
        if current > self._window_start:
            self._requests_made = 0
            self._window_start = current

    def can_make_request(self) -> bool:
        with self._lock:
            self._maybe_reset()
            return self._requests_made < self.minute_limit

    def record_request(self) -> None:
        with self._lock:
            self._maybe_reset()
            self._requests_made += 1

    def get_remaining(self) -> int:
        with self._lock:
            self._maybe_reset()
            return max(0, self.minute_limit - self._requests_made)

    def seconds_until_reset(self) -> float:
        next_window = self._window_start + timedelta(minutes=1)
        delta = next_window - datetime.now()
        return max(0.0, delta.total_seconds())

    def acquire(self, blocking: bool = True) -> None:
        while True:
            with self._lock:
                self._maybe_reset()
                if self._requests_made < self.minute_limit:
                    self._requests_made += 1
                    return
                if not blocking:
                    raise Exception(
                        f"Rate limit reached ({self.minute_limit} req/min). "
                        f"Resets in {self.seconds_until_reset():.0f}s."
                    )
                wait = self.seconds_until_reset()
            time.sleep(wait)
