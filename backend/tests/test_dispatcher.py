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
            base_delay=0.01,
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
            max_attempts=1,
            base_delay=0.01,
            max_consecutive_failures=5,
            cooloff_seconds=10.0
        )

        for i in range(5):
            with self.assertRaises(RuntimeError):
                await dispatcher.call(always_failing_fn)

        self.assertEqual(dispatcher.state, "OPEN")

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
            cooloff_seconds=0.15
        )

        for _ in range(2):
            with self.assertRaises(RuntimeError):
                await dispatcher.call(failing_fn)

        self.assertEqual(dispatcher.state, "OPEN")

        with self.assertRaises(CircuitBreakerOpenError):
            await dispatcher.call(succeeding_fn)

        await asyncio.sleep(0.2)

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

    async def test_circuit_breaker_half_open_failure_re_trips(self):
        dispatcher = Dispatcher(
            max_concurrent=3,
            max_attempts=1,
            base_delay=0.01,
            max_consecutive_failures=2,
            cooloff_seconds=0.1
        )

        async def failing_fn():
            raise RuntimeError("Fail in HALF_OPEN")

        for _ in range(2):
            with self.assertRaises(RuntimeError):
                await dispatcher.call(failing_fn)
        self.assertEqual(dispatcher.state, "OPEN")

        await asyncio.sleep(0.12)

        with self.assertRaises(RuntimeError):
            await dispatcher.call(failing_fn)
        self.assertEqual(dispatcher.state, "OPEN")

class TestDispatcherArchitectureAndContracts(unittest.TestCase):
    def test_test_a_dispatcher_importability(self):
        import backend
        import backend.dispatcher

        from backend.dispatcher import (
            Dispatcher,
            CircuitBreakerOpenError,
            CircuitState,
            default_dispatcher,
            scholarly_dispatcher,
            s2_dispatcher,
        )
        self.assertIsNotNone(Dispatcher)
        self.assertIsNotNone(CircuitBreakerOpenError)
        self.assertIsNotNone(CircuitState)
        self.assertIsNotNone(default_dispatcher)
        self.assertIsNotNone(scholarly_dispatcher)
        self.assertIsNotNone(s2_dispatcher)

        from backend import (
            Dispatcher as PkgDispatcher,
            CircuitBreakerOpenError as PkgCircuitBreakerOpenError,
            CircuitState as PkgCircuitState,
            default_dispatcher as pkg_default_dispatcher,
            scholarly_dispatcher as pkg_scholarly_dispatcher,
            s2_dispatcher as pkg_s2_dispatcher,
        )
        self.assertIsNotNone(PkgDispatcher)
        self.assertIsNotNone(PkgCircuitBreakerOpenError)
        self.assertIsNotNone(PkgCircuitState)
        self.assertIsNotNone(pkg_default_dispatcher)
        self.assertIsNotNone(pkg_scholarly_dispatcher)
        self.assertIsNotNone(pkg_s2_dispatcher)

    def test_test_b_shared_singleton_identity(self):
        import backend
        import backend.dispatcher

        self.assertIs(backend.default_dispatcher, backend.dispatcher.default_dispatcher)
        self.assertIs(backend.scholarly_dispatcher, backend.dispatcher.scholarly_dispatcher)
        self.assertIs(backend.s2_dispatcher, backend.dispatcher.s2_dispatcher)
        self.assertIs(backend.CircuitState, backend.dispatcher.CircuitState)

        self.assertIsInstance(backend.default_dispatcher, backend.dispatcher.Dispatcher)
        self.assertIsInstance(backend.scholarly_dispatcher, backend.dispatcher.Dispatcher)
        self.assertIsInstance(backend.s2_dispatcher, backend.dispatcher.Dispatcher)

    def test_test_c_circuit_state_contract(self):
        import json
        from backend.dispatcher import CircuitState, Dispatcher

        self.assertEqual(CircuitState.CLOSED.value, "CLOSED")
        self.assertEqual(CircuitState.OPEN.value, "OPEN")
        self.assertEqual(CircuitState.HALF_OPEN.value, "HALF_OPEN")

        self.assertEqual(CircuitState.CLOSED, "CLOSED")
        self.assertEqual(CircuitState.OPEN, "OPEN")
        self.assertEqual(CircuitState.HALF_OPEN, "HALF_OPEN")
        self.assertIsInstance(CircuitState.CLOSED, str)
        self.assertEqual(str(CircuitState.CLOSED), "CLOSED")

        serialized = json.dumps({"state": CircuitState.CLOSED})
        self.assertEqual(serialized, '{"state": "CLOSED"}')

        d = Dispatcher()
        self.assertEqual(d.state, "CLOSED")
        self.assertEqual(d.state, CircuitState.CLOSED)
        self.assertIn(d.state, ("CLOSED", "OPEN", "HALF_OPEN"))
        self.assertIn(d.state, (CircuitState.CLOSED, CircuitState.OPEN, CircuitState.HALF_OPEN))

    def test_test_e_telemetry_and_status_reporting(self):
        import json
        from backend.telemetry import get_telemetry_status
        from backend.dispatcher import default_dispatcher, scholarly_dispatcher, s2_dispatcher

        status = get_telemetry_status()
        self.assertIn("circuit_breaker_state", status)
        self.assertIn("scholarly_breaker_state", status)
        self.assertIn("s2_breaker_state", status)

        self.assertEqual(status["circuit_breaker_state"], default_dispatcher.state)
        self.assertEqual(status["scholarly_breaker_state"], scholarly_dispatcher.state)
        self.assertEqual(status["s2_breaker_state"], s2_dispatcher.state)

        encoded = json.dumps(status)
        self.assertIn('"circuit_breaker_state": "CLOSED"', encoded)

    def test_test_f_scholarly_dispatcher_usage(self):
        import backend.scholarly as scholarly
        from backend.dispatcher import scholarly_dispatcher, s2_dispatcher

        self.assertIs(scholarly.scholarly_dispatcher, scholarly_dispatcher)
        self.assertIs(scholarly.s2_dispatcher, s2_dispatcher)
        self.assertEqual(scholarly.s2_dispatcher.min_interval_seconds, 1.35)
        self.assertEqual(scholarly.s2_dispatcher.max_concurrent, 1)

if __name__ == "__main__":
    unittest.main()
