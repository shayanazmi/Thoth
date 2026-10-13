import asyncio
import time
import random
import logging
import inspect
from enum import Enum
from typing import Callable, Any, Dict, Optional

logger = logging.getLogger("ThothDispatcher")

class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __str__(self) -> str:
        return self.value

class CircuitBreakerOpenError(Exception):
    pass

class Dispatcher:
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

        self._state: CircuitState = CircuitState.CLOSED
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
    def state(self) -> CircuitState:
        return self._state

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    async def _check_and_update_circuit_breaker(self):
        async with self._lock:
            now = time.time()
            if self._state == CircuitState.OPEN:
                if now - self._last_failure_time >= self.cooloff_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_in_flight = True
                    logger.info(f"[DISPATCHER CIRCUIT BREAKER] Cooloff of {self.cooloff_seconds}s expired. Transitioning to HALF_OPEN (permitting 1 test call).")
                    print(f"\n[INFO] [DISPATCHER] Circuit Breaker transitioned to HALF_OPEN (1 test call permitted).")
                else:
                    remaining = round(self.cooloff_seconds - (now - self._last_failure_time), 1)
                    logger.warning(f"[DISPATCHER CIRCUIT BREAKER] Blocked call: State is OPEN. {remaining}s remaining in cooloff.")
                    raise CircuitBreakerOpenError(f"Circuit Breaker is OPEN. Blocked for cooloff ({remaining}s remaining).")
            elif self._state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight:
                    logger.warning("[DISPATCHER CIRCUIT BREAKER] Blocked call: State is HALF_OPEN and test call is already in flight.")
                    raise CircuitBreakerOpenError("Circuit Breaker is HALF_OPEN. Test call already in progress.")
                else:
                    self._half_open_in_flight = True

    async def _record_success(self):
        async with self._lock:
            if self._state in (CircuitState.OPEN, CircuitState.HALF_OPEN):
                logger.info(f"[DISPATCHER CIRCUIT BREAKER] Test call succeeded! Transitioning state from {self._state} -> CLOSED.")
                print(f"\n[INFO] [DISPATCHER] Circuit Breaker recovered: {self._state} -> CLOSED.")
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._half_open_in_flight = False

    async def _record_failure(self):
        async with self._lock:
            self._consecutive_failures += 1
            now = time.time()
            self._last_failure_time = now

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._half_open_in_flight = False
                logger.warning(f"[DISPATCHER CIRCUIT BREAKER] Test call failed in HALF_OPEN. Tripping back to OPEN for {self.cooloff_seconds}s.")
                print(f"\n[WARNING] [DISPATCHER] Test call failed in HALF_OPEN. Tripping back to OPEN for {self.cooloff_seconds}s.")
            elif self._consecutive_failures >= self.max_consecutive_failures:
                self._state = CircuitState.OPEN
                logger.warning(f"[DISPATCHER CIRCUIT BREAKER] {self._consecutive_failures} consecutive failures hit limit ({self.max_consecutive_failures}). Tripping to OPEN for {self.cooloff_seconds}s.")
                print(f"\n[WARNING] [DISPATCHER] Circuit Breaker TRIPPED -> OPEN for {self.cooloff_seconds}s ({self._consecutive_failures} consecutive failures).")

    async def _enforce_rate_limit(self):
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
        last_exception = None

        for attempt in range(1, self.max_attempts + 1):
            await self._check_and_update_circuit_breaker()

            try:
                async with self._semaphore:
                    await self._enforce_rate_limit()

                    logger.debug(f"[DISPATCHER] Executing call attempt {attempt}/{self.max_attempts} for {getattr(fn, '__name__', str(fn))}")
                    if inspect.iscoroutinefunction(fn) or (hasattr(fn, "__call__") and inspect.iscoroutinefunction(fn.__call__)):
                        res = await fn(*args, **kwargs)
                    else:
                        res = await asyncio.to_thread(fn, *args, **kwargs)

                    if self.min_interval_seconds > 0.0:
                        self._last_call_time = time.time()

                await self._record_success()
                return res

            except Exception as e:
                last_exception = e

                is_non_retryable = False
                if hasattr(e, "response") and hasattr(e.response, "status_code"):
                    if e.response.status_code in {400, 401, 403, 404, 422}:
                        is_non_retryable = True

                if is_non_retryable:
                    logger.debug(f"[DISPATCHER] Non-retryable HTTP {getattr(e.response, 'status_code', '')} client error for {getattr(fn, '__name__', str(fn))}. Failing fast without backoff.")
                    raise last_exception

                await self._record_failure()

                if self._state == CircuitState.OPEN:
                    logger.warning(f"[DISPATCHER] Call attempt {attempt}/{self.max_attempts} failed and Circuit Breaker is now OPEN.")
                    raise last_exception

                if attempt == self.max_attempts:
                    logger.warning(f"[DISPATCHER] All {self.max_attempts} attempts failed for {getattr(fn, '__name__', str(fn))}.")
                    raise last_exception

                delay = self.base_delay * (2 ** (attempt - 1))
                jitter = random.uniform(0, 0.5 * delay)
                total_delay = delay + jitter

                logger.warning(f"[DISPATCHER] Call attempt {attempt}/{self.max_attempts} failed with {type(e).__name__}: {e}. Retrying in {total_delay:.2f}s...")
                print(f"\n[WARNING] [DISPATCHER] Attempt {attempt}/{self.max_attempts} failed ({type(e).__name__}: {e}). Retrying in {total_delay:.2f}s...")
                await asyncio.sleep(total_delay)

        raise last_exception

default_dispatcher = Dispatcher()

scholarly_dispatcher = Dispatcher(
    max_concurrent=3,
    max_attempts=3,
    base_delay=1.0,
    max_consecutive_failures=5,
    cooloff_seconds=30.0
)

s2_dispatcher = Dispatcher(
    max_concurrent=1,
    min_interval_seconds=1.35,
    max_attempts=3,
    base_delay=3.0,
    max_consecutive_failures=8,
    cooloff_seconds=10.0
)

__all__ = [
    "Dispatcher",
    "CircuitBreakerOpenError",
    "CircuitState",
    "default_dispatcher",
    "scholarly_dispatcher",
    "s2_dispatcher",
]

