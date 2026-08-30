import asyncio
import time
import random
import logging
import inspect
from typing import Callable, Any, Dict, Optional

logger = logging.getLogger("ThothDispatcher")


class CircuitBreakerOpenError(Exception):
    """Raised when call is blocked because Circuit Breaker is in OPEN state."""
    pass


class Dispatcher:
    """
    Central concurrency and resilience dispatcher.
    Provides asyncio.Semaphore concurrency capping, rate-limit pacing (token bucket / interval),
    exponential backoff with jitter, and a 3-state Circuit Breaker (CLOSED, OPEN, HALF_OPEN).
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        max_attempts: int = 4,
        base_delay: float = 1.0,
        max_consecutive_failures: int = 5,
        cooloff_seconds: float = 30.0,
        min_interval_seconds: float = 0.0
    ):
        self.max_concurrent = max_concurrent
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_consecutive_failures = max_consecutive_failures
        self.cooloff_seconds = cooloff_seconds
        self.min_interval_seconds = min_interval_seconds

        self._state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._consecutive_failures = 0
        self._last_failure_time = 0.0
        self._last_call_time = 0.0
        self._half_open_in_flight = False
        self._semaphores = {}
        self._locks = {}
        self._rate_locks = {}

    @property
    def _semaphore(self) -> asyncio.Semaphore:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.Semaphore(self.max_concurrent)
        if loop not in self._semaphores:
            self._semaphores[loop] = asyncio.Semaphore(self.max_concurrent)
        return self._semaphores[loop]

    @property
    def _lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.Lock()
        if loop not in self._locks:
            self._locks[loop] = asyncio.Lock()
        return self._locks[loop]

    @property
    def _rate_lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.Lock()
        if loop not in self._rate_locks:
            self._rate_locks[loop] = asyncio.Lock()
        return self._rate_locks[loop]


    @property
    def state(self) -> str:
        return self._state

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    async def _check_and_update_circuit_breaker(self):
        """Validates circuit breaker state prior to attempting a call."""
        async with self._lock:
            now = time.time()
            if self._state == "OPEN":
                if now - self._last_failure_time >= self.cooloff_seconds:
                    self._state = "HALF_OPEN"
                    self._half_open_in_flight = True
                    logger.info(f"[DISPATCHER CIRCUIT BREAKER] Cooloff of {self.cooloff_seconds}s expired. Transitioning to HALF_OPEN (permitting 1 test call).")
                    print(f"\n[INFO] [DISPATCHER] Circuit Breaker transitioned to HALF_OPEN (1 test call permitted).")
                else:
                    remaining = round(self.cooloff_seconds - (now - self._last_failure_time), 1)
                    logger.warning(f"[DISPATCHER CIRCUIT BREAKER] Blocked call: State is OPEN. {remaining}s remaining in cooloff.")
                    raise CircuitBreakerOpenError(f"Circuit Breaker is OPEN. Blocked for cooloff ({remaining}s remaining).")
            elif self._state == "HALF_OPEN":
                if self._half_open_in_flight:
                    logger.warning("[DISPATCHER CIRCUIT BREAKER] Blocked call: State is HALF_OPEN and test call is already in flight.")
                    raise CircuitBreakerOpenError("Circuit Breaker is HALF_OPEN. Test call already in progress.")
                else:
                    self._half_open_in_flight = True

    async def _record_success(self):
        """Records call success, resetting failure counters and closing circuit breaker."""
        async with self._lock:
            if self._state in ("OPEN", "HALF_OPEN"):
                logger.info(f"[DISPATCHER CIRCUIT BREAKER] Test call succeeded! Transitioning state from {self._state} -> CLOSED.")
                print(f"\n[INFO] [DISPATCHER] Circuit Breaker recovered: {self._state} -> CLOSED.")
            self._state = "CLOSED"
            self._consecutive_failures = 0
            self._half_open_in_flight = False

    async def _record_failure(self):
        """Records call failure, incrementing failure counts and tripping circuit breaker if threshold hit."""
        async with self._lock:
            self._consecutive_failures += 1
            now = time.time()
            self._last_failure_time = now

            if self._state == "HALF_OPEN":
                self._state = "OPEN"
                self._half_open_in_flight = False
                logger.warning(f"[DISPATCHER CIRCUIT BREAKER] Test call failed in HALF_OPEN. Tripping back to OPEN for {self.cooloff_seconds}s.")
                print(f"\n[WARNING] [DISPATCHER] Test call failed in HALF_OPEN. Tripping back to OPEN for {self.cooloff_seconds}s.")
            elif self._consecutive_failures >= self.max_consecutive_failures:
                self._state = "OPEN"
                logger.warning(f"[DISPATCHER CIRCUIT BREAKER] {self._consecutive_failures} consecutive failures hit limit ({self.max_consecutive_failures}). Tripping to OPEN for {self.cooloff_seconds}s.")
                print(f"\n[WARNING] [DISPATCHER] Circuit Breaker TRIPPED -> OPEN for {self.cooloff_seconds}s ({self._consecutive_failures} consecutive failures).")

    async def _enforce_rate_limit(self):
        """Enforces minimum inter-request delay if min_interval_seconds is set."""
        if self.min_interval_seconds <= 0.0:
            return
        async with self._rate_lock:
            now = time.time()
            elapsed = now - self._last_call_time
            if elapsed < self.min_interval_seconds:
                sleep_needed = self.min_interval_seconds - elapsed
                logger.debug(f"[DISPATCHER RATE LIMIT] Pacing call: sleeping {sleep_needed:.2f}s")
                await asyncio.sleep(sleep_needed)
            self._last_call_time = time.time()

    async def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Executes fn(*args, **kwargs) with concurrency capping, rate-limit pacing,
        exponential backoff retries with jitter, and circuit breaker protection.
        Supports both coroutines and sync callables.
        """
        last_exception = None

        for attempt in range(1, self.max_attempts + 1):
            # Check circuit breaker before attempting
            await self._check_and_update_circuit_breaker()

            try:
                async with self._semaphore:
                    # Enforce rate-limiting interval pacing under concurrency lock
                    await self._enforce_rate_limit()

                    logger.debug(f"[DISPATCHER] Executing call attempt {attempt}/{self.max_attempts} for {getattr(fn, '__name__', str(fn))}")
                    if inspect.iscoroutinefunction(fn) or (hasattr(fn, "__call__") and inspect.iscoroutinefunction(fn.__call__)):
                        res = await fn(*args, **kwargs)
                    else:
                        res = await asyncio.to_thread(fn, *args, **kwargs)

                    # Update last call completion timestamp for rate limit pacing
                    if self.min_interval_seconds > 0.0:
                        self._last_call_time = time.time()

                await self._record_success()
                return res


            except Exception as e:
                last_exception = e

                # Determine if error is client error that should NOT be retried (404, 400, 401, 403)
                is_non_retryable = False
                if hasattr(e, "response") and hasattr(e.response, "status_code"):
                    if e.response.status_code in {400, 401, 403, 404, 422}:
                        is_non_retryable = True

                if is_non_retryable:
                    logger.debug(f"[DISPATCHER] Non-retryable HTTP {getattr(e.response, 'status_code', '')} client error for {getattr(fn, '__name__', str(fn))}. Failing fast without backoff.")
                    raise last_exception

                await self._record_failure()

                # If circuit breaker tripped OPEN during this attempt, raise immediately
                if self._state == "OPEN":
                    logger.warning(f"[DISPATCHER] Call attempt {attempt}/{self.max_attempts} failed and Circuit Breaker is now OPEN.")
                    raise last_exception

                if attempt == self.max_attempts:
                    logger.warning(f"[DISPATCHER] All {self.max_attempts} attempts failed for {getattr(fn, '__name__', str(fn))}.")
                    raise last_exception

                # Calculate exponential backoff delay with random jitter (up to 50% of delay)
                delay = self.base_delay * (2 ** (attempt - 1))
                jitter = random.uniform(0, 0.5 * delay)
                total_delay = delay + jitter

                logger.warning(f"[DISPATCHER] Call attempt {attempt}/{self.max_attempts} failed with {type(e).__name__}: {e}. Retrying in {total_delay:.2f}s...")
                print(f"\n[WARNING] [DISPATCHER] Attempt {attempt}/{self.max_attempts} failed ({type(e).__name__}: {e}). Retrying in {total_delay:.2f}s...")
                await asyncio.sleep(total_delay)

        raise last_exception


# Global default dispatcher instance
default_dispatcher = Dispatcher()

# Default academic scholarly dispatcher
scholarly_dispatcher = Dispatcher(
    max_concurrent=3,
    max_attempts=3,
    base_delay=1.0,
    max_consecutive_failures=5,
    cooloff_seconds=30.0
)

# Dedicated Semantic Scholar Dispatcher (strict 1 req/1.35s pacing to satisfy 1 req/sec limit)
s2_dispatcher = Dispatcher(
    max_concurrent=1,
    min_interval_seconds=1.35,
    max_attempts=3,
    base_delay=3.0,
    max_consecutive_failures=8,
    cooloff_seconds=10.0
)



