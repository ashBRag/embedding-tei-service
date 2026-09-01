"""Async rate limiter for hosted embedding APIs with TPM + RPM limits.

Voyage (and similar hosted providers) cap usage on a rolling per-minute
window along two axes at once - tokens per minute (TPM) and requests per
minute (RPM). `RateLimiter.acquire` blocks the caller until both budgets
have room for the next request, so a caller that just calls `acquire` before
every outbound HTTP request never needs to handle 429s from normal traffic
volume itself.

Generic: takes plain `ModelLimits`, not any project's settings class, so
it's reusable for any hosted provider (Voyage today; OpenAI/Cohere etc.
later) that needs the same two-axis budgeting.
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass

__all__ = ["ModelLimits", "RateLimiter"]

_WINDOW_SECONDS = 60.0


@dataclass(frozen=True)
class ModelLimits:
    """A hosted model's rolling-window rate caps.

    tpm: Tokens per minute allowed by the provider for this model.
    rpm: Requests per minute allowed by the provider for this model.

    Distinct from any per-request size caps (max texts/tokens per request) -
    those bound the shape of a single request and belong in batch planning
    (see app/integrations/base.py's plan_token_aware_batches), not here. tpm
    and rpm bound the *rate* of requests over time, which is what
    RateLimiter.acquire throttles against.
    """

    tpm: int
    rpm: int


class RateLimiter:
    """Tracks token/request usage in a rolling 60s window and blocks callers over budget.

    Not a token-bucket (which would allow smooth-but-unbounded refill) -
    uses an explicit rolling window of past request timestamps/costs so the
    limiter's behavior maps directly onto how providers like Voyage
    describe their limits ("N tokens per minute").

    Safe for concurrent callers: an asyncio.Lock serializes the
    check-and-reserve so two concurrent `acquire` calls can't both observe
    spare budget and jointly exceed it.
    """

    def __init__(self, limits: ModelLimits, *, clock: type[time] = time):
        """Store the limits to enforce; `clock` is injectable for tests."""
        self.limits = limits
        self._clock = clock
        self._lock = asyncio.Lock()
        # Each entry: (timestamp, tokens_used) for one past request.
        self._history: deque[tuple[float, int]] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - _WINDOW_SECONDS
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

    def _usage(self) -> tuple[int, int]:
        """Return (tokens_used, requests_used) currently within the window."""
        return sum(tokens for _, tokens in self._history), len(self._history)

    async def acquire(self, tokens: int) -> None:
        """Block until a request costing `tokens` fits within both the TPM and RPM budgets.

        Reserves the request (records it in the window) before returning,
        so a burst of concurrent callers is serialized against the same
        budget rather than each independently checking a stale snapshot.
        """
        async with self._lock:
            while True:
                now = self._clock.monotonic()
                self._prune(now)
                tokens_used, requests_used = self._usage()

                fits_tokens = tokens_used + tokens <= self.limits.tpm
                fits_requests = requests_used + 1 <= self.limits.rpm
                if fits_tokens and fits_requests:
                    self._history.append((now, tokens))
                    return

                # Wait until the oldest entry ages out of the window, then re-check.
                wait_seconds = (self._history[0][0] + _WINDOW_SECONDS) - now
                await asyncio.sleep(max(wait_seconds, 0.01))
