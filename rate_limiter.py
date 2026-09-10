"""
Rate limiter for CareerMatch AI bot.
Prevents abuse by limiting the number of analyses per user per time window.
"""

import time
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token-bucket-style rate limiter per user.

    Tracks analysis requests per user_id within a rolling time window.
    """

    def __init__(self, max_requests: int = 5, window_seconds: int = 3600):
        """
        Args:
            max_requests: Maximum analyses allowed per window.
            window_seconds: Time window in seconds (default: 1 hour).
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[int, list[float]] = defaultdict(list)

    def is_allowed(self, user_id: int) -> bool:
        """Check if the user is allowed to make another request."""
        self._cleanup(user_id)
        return len(self._requests[user_id]) < self.max_requests

    def record(self, user_id: int) -> None:
        """Record a new request for the user."""
        self._cleanup(user_id)
        self._requests[user_id].append(time.time())
        logger.debug(
            f"User {user_id}: {len(self._requests[user_id])}/{self.max_requests} "
            f"requests used in current window."
        )

    def remaining(self, user_id: int) -> int:
        """Return the number of remaining requests for the user."""
        self._cleanup(user_id)
        return max(0, self.max_requests - len(self._requests[user_id]))

    def retry_after(self, user_id: int) -> int:
        """Return seconds until the oldest request expires (i.e., a slot opens)."""
        self._cleanup(user_id)
        if not self._requests[user_id]:
            return 0
        oldest = self._requests[user_id][0]
        return max(0, int(self.window_seconds - (time.time() - oldest)))

    def _cleanup(self, user_id: int) -> None:
        """Remove expired request timestamps."""
        now = time.time()
        cutoff = now - self.window_seconds
        self._requests[user_id] = [
            t for t in self._requests[user_id] if t > cutoff
        ]


# Global rate limiter instance — 5 analyses per hour per user
rate_limiter = RateLimiter(max_requests=5, window_seconds=3600)
