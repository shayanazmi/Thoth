import unittest
import asyncio
import time
from backend.dispatcher import Dispatcher, CircuitBreakerOpenError


class TestDispatcher(unittest.IsolatedAsyncioTestCase):

    async def test_flaky_function_retries_and_succeeds(self):
        attempts = 0

        async def flaky_async_fn():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError(f"Simulated failure attempt {attempts}")
            return "SUCCESS"

        dispatcher = Dispatcher(
            max_concurrent=3,
            max_attempts=4,
            base_delay=0.01,  # Fast delays for test speed
            max_consecutive_failures=5,
            cooloff_seconds=1.0
        )

        result = await dispatcher.call(flaky_async_fn)
        self.assertEqual(result, "SUCCESS")
        self.assertEqual(attempts, 3)
        self.assertEqual(dispatcher.state, "CLOSED")
        self.assertEqual(dispatcher.consecutive_failures, 0)

    async def test_circuit_breaker_trips_on_repeated_failures(self):
        async def always_failing_fn():
            raise RuntimeError("Permanent failure")

        dispatcher = Dispatcher(
            max_concurrent=3,
            max_attempts=1,  # 1 attempt per call to quickly count consecutive failures
            base_delay=0.01,
            max_consecutive_failures=5,
            cooloff_seconds=10.0
        )

        # 5 consecutive call failures
        for i in range(5):
            with self.assertRaises(RuntimeError):
                await dispatcher.call(always_failing_fn)

        # The 5th failure trips the Circuit Breaker to OPEN
        self.assertEqual(dispatcher.state, "OPEN")

        # The 6th call must be blocked immediately by CircuitBreakerOpenError
        with self.assertRaises(CircuitBreakerOpenError) as cm:
            await dispatcher.call(always_failing_fn)

        self.assertIn("Circuit Breaker is OPEN", str(cm.exception))

    async def test_circuit_breaker_cooloff_and_half_open_recovery(self):
        async def failing_fn():
            raise RuntimeError("Fail")

        async def succeeding_fn():
            return "RECOVERED"

        dispatcher = Dispatcher(
            max_concurrent=3,
            max_attempts=1,
            base_delay=0.01,
            max_consecutive_failures=2,
            cooloff_seconds=0.15  # Short 150ms cooloff for testing
        )

        # Trip to OPEN with 2 failures
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                await dispatcher.call(failing_fn)

        self.assertEqual(dispatcher.state, "OPEN")

        # Call immediately while in cooloff -> CircuitBreakerOpenError
        with self.assertRaises(CircuitBreakerOpenError):
            await dispatcher.call(succeeding_fn)

        # Sleep past cooloff period
        await asyncio.sleep(0.2)

        # Test call transitions HALF_OPEN -> CLOSED on success
        res = await dispatcher.call(succeeding_fn)
        self.assertEqual(res, "RECOVERED")
        self.assertEqual(dispatcher.state, "CLOSED")
        self.assertEqual(dispatcher.consecutive_failures, 0)

    async def test_concurrency_semaphore_capping(self):
        in_flight = 0
        max_seen_in_flight = 0

        async def worker_fn():
            nonlocal in_flight, max_seen_in_flight
            in_flight += 1
            if in_flight > max_seen_in_flight:
                max_seen_in_flight = in_flight
            await asyncio.sleep(0.05)
            in_flight -= 1
            return "OK"

        dispatcher = Dispatcher(max_concurrent=2, max_attempts=1, base_delay=0.01)

        tasks = [dispatcher.call(worker_fn) for _ in range(6)]
        results = await asyncio.gather(*tasks)

        self.assertEqual(results, ["OK"] * 6)
        self.assertLessEqual(max_seen_in_flight, 2)


if __name__ == "__main__":
    unittest.main()
