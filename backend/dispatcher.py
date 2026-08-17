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
    Provides asyncio.Semaphore concurrency capping, exponential backoff with jitter,
    and a 3-state Circuit Breaker (CLOSED, OPEN, HALF_OPEN).
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        max_attempts: int = 4,
        base_delay: float = 1.0,
        max_consecutive_failures: int = 5,
        cooloff_seconds: float = 30.0
    ):
        self.max_concurrent = max_concurrent
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_consecutive_failures = max_consecutive_failures
        self.cooloff_seconds = cooloff_seconds

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._consecutive_failures = 0
        self._last_failure_time = 0.0
        self._half_open_in_flight = False
        self._lock = asyncio.Lock()

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

    async def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Executes fn(*args, **kwargs) with concurrency capping, exponential backoff retries with jitter,
        and circuit breaker protection. Supports both coroutines and sync callables.
        """
        last_exception = None

        for attempt in range(1, self.max_attempts + 1):
            # Check circuit breaker before attempting
            await self._check_and_update_circuit_breaker()

            try:
                async with self._semaphore:
                    logger.debug(f"[DISPATCHER] Executing call attempt {attempt}/{self.max_attempts} for {getattr(fn, '__name__', str(fn))}")
                    if inspect.iscoroutinefunction(fn) or (hasattr(fn, "__call__") and inspect.iscoroutinefunction(fn.__call__)):
                        res = await fn(*args, **kwargs)
                    else:
                        res = await asyncio.to_thread(fn, *args, **kwargs)

                await self._record_success()
                return res

            except Exception as e:
                last_exception = e
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
