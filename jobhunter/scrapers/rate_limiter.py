import asyncio
import logging
import random

logger = logging.getLogger(__name__)


class RateLimiter:
    """Async rate limiter with configurable delay and jitter."""

    def __init__(self, delay_seconds: float, jitter_fraction: float = 0.3) -> None:
        self._delay = delay_seconds
        self._jitter = jitter_fraction

    async def wait(self) -> None:
        """Sleep for delay +/- jitter seconds."""
        jitter = self._delay * self._jitter * random.uniform(-1, 1)
        sleep_time = max(0, self._delay + jitter)
        if sleep_time > 0:
            logger.debug("Rate limiter: sleeping %.2fs", sleep_time)
            await asyncio.sleep(sleep_time)
