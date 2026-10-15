"""Real isolated filesystem caches and forked workers; no external services."""

from contextlib import contextmanager, nullcontext
import multiprocessing
import inspect
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
import revenue_kpis
import wholesale_kpis
import warehouse_cache
import test_cache_coverage as coverage


class CacheConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.server = Flask(__name__)
        self.server.config["KPI_CACHE_LOCK_TIMEOUT_SECONDS"] = 5.0
        self.server.extensions["executive_query_lock_dir"] = Path(self.directory.name)
        revenue_kpis.cache.init_app(
            self.server,
            config={
                "CACHE_TYPE": "FileSystemCache",
                "CACHE_DIR": str(Path(self.directory.name) / "cache"),
                "CACHE_THRESHOLD": 500,
            },
        )
        self.context = self.server.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        self.process_context = multiprocessing.get_context("fork")
        self.count = self.process_context.Value("i", 0)
        self.failure = self.process_context.Value("i", 0)
        self.started = self.process_context.Event()
        self.release = self.process_context.Event()
        self.release.set()
        patcher = patch("google.cloud.bigquery.Client")
        factory = patcher.start()
        self.addCleanup(patcher.stop)
        factory.return_value.__enter__.return_value.query.side_effect = self.query
        self.workers = []
        self.addCleanup(self.stop_workers)

    def stop_workers(self):
        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
            worker.join(timeout=5)

    def query(self, *args, **kwargs):
        with self.count.get_lock():
            self.count.value += 1
            marker = self.count.value
        self.started.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("test warehouse release deadline")
        with self.failure.get_lock():
            fail = self.failure.value
            self.failure.value = 0
        if fail:
            raise RuntimeError("synthetic warehouse failure")
        job = Mock()
        job.result.return_value = [
            {
                "source_rows": 1,
                "query_marker": marker,
                "monthly": [],
                "active_accounts": marker,
                "wholesale_orders": marker,
                "total_reseller_revenue": marker,
            }
        ]
        return job

    def start(self, function):
        worker = self.process_context.Process(target=function)
        self.workers.append(worker)
        worker.start()
        return worker

    def joined(self, worker):
        worker.join(timeout=8)
        self.assertFalse(worker.is_alive(), "worker deadlocked")
        self.assertEqual(worker.exitcode, 0)

    def concurrent(self, loader, arguments, *, clock=None):
        modes = ["positional", "keyword"]
        if any(
            p.default is not inspect.Parameter.empty
            for p in inspect.signature(loader).parameters.values()
        ):
            modes.append("defaults")
        barrier = self.process_context.Barrier(len(modes) + 1)
        entered = self.process_context.Value("i", 0)
        all_entered = self.process_context.Event()
        original_lock = warehouse_cache.query_lock
        self.release.clear()

        @contextmanager
        def observed_lock(key):
            with entered.get_lock():
                entered.value += 1
                if entered.value >= len(modes):
                    all_entered.set()
            with original_lock(key):
                yield

        results = self.process_context.Queue()
        self.addCleanup(results.close)

        def fetch(mode):
            try:
                with self.server.app_context():
                    with (
                        patch("cachelib.file.time", return_value=clock)
                        if clock is not None
                        else nullcontext()
                    ):
                        barrier.wait(timeout=5)
                        if mode == "positional":
                            result = loader(*arguments.values())
                        elif mode == "keyword":
                            result = loader(**arguments)
                        else:
                            required = {
                                name: arguments[name]
                                for name, p in inspect.signature(
                                    loader
                                ).parameters.items()
                                if p.default is inspect.Parameter.empty
                            }
                            result = loader(**required)
                        results.put(("ok", result))
            except Exception as error:
                results.put((type(error).__name__, str(error)))

        with patch("warehouse_cache.query_lock", observed_lock):
            workers = [self.start(lambda mode=mode: fetch(mode)) for mode in modes]
            barrier.wait(timeout=5)
            self.assertTrue(
                all_entered.wait(timeout=5), "workers did not reach the cold lock"
            )
            self.release.set()
        for worker in workers:
            self.joined(worker)
        values = [results.get(timeout=2) for _ in workers]
        self.assertEqual([value[0] for value in values], ["ok"] * len(modes))
        self.assertTrue(all(value[1] == values[0][1] for value in values))
        return values[0][1]

    def test_all_direct_loaders_coalesce_cold_and_expired_keys_across_processes(self):
        direct = [
            loader
            for loader in coverage.LOADERS
            if loader is not wholesale_kpis.load_wholesale_comparison
        ]
        for loader in direct:
            with self.subTest(loader=loader.__name__):
                revenue_kpis.cache.clear()  # Only this test's temporary backend.
                arguments = coverage.CacheCoverageTests.arguments(loader)
                before = self.count.value
                cold = self.concurrent(loader, arguments)
                self.assertEqual(self.count.value, before + 1)
                future = time.time() + loader.cache_timeout + 2
                expired = self.concurrent(loader, arguments, clock=future)
                self.assertEqual(self.count.value, before + 2)
                self.assertNotEqual(cold, expired)

    def test_none_is_cached_atomically_and_coalesced(self):

        # Exercise the production loader's empty warehouse response.
        def empty_query(*args, **kwargs):
            with self.count.get_lock():
                self.count.value += 1
            if not self.release.wait(timeout=5):
                raise RuntimeError("test warehouse release deadline")
            job = Mock()
            job.result.return_value = []
            return job

        with patch("google.cloud.bigquery.Client") as factory:
            factory.return_value.__enter__.return_value.query.side_effect = empty_query
            loader = revenue_kpis.load_revenue_kpis
            arguments = {"project": "test-project", "dataset": "analytics"}
            self.assertIsNone(self.concurrent(loader, arguments))
            self.assertIsNone(loader(**arguments))
            self.assertEqual(self.count.value, 1)

    def test_process_exception_is_not_cached_and_follower_recovers(self):
        self.failure.value = 1
        loader = revenue_kpis.load_revenue_kpis
        arguments = ("test-project", "analytics")
        errors = self.process_context.Queue()
        self.addCleanup(errors.close)

        def fail():
            try:
                loader(*arguments)
            except RuntimeError as error:
                errors.put(str(error))

        worker = self.start(fail)
        self.joined(worker)
        self.assertEqual(errors.get(timeout=2), "synthetic warehouse failure")
        result = loader(*arguments)
        self.assertEqual(self.count.value, 2)
        self.assertEqual(loader(*arguments), result)
        self.assertEqual(self.count.value, 2)

    def test_timeout_does_not_publish_and_terminated_worker_releases_lock(self):
        self.server.config["KPI_CACHE_LOCK_TIMEOUT_SECONDS"] = 0.2
        loader = revenue_kpis.load_revenue_kpis
        arguments = ("test-project", "analytics")

        def interrupted_query(*args, **kwargs):
            with self.count.get_lock():
                self.count.value += 1
            self.started.set()
            # No multiprocessing semaphore can be abandoned by termination.
            time.sleep(30)
            raise AssertionError("worker should have been terminated")

        with patch("google.cloud.bigquery.Client") as factory:
            factory.return_value.__enter__.return_value.query.side_effect = (
                interrupted_query
            )
            worker = self.start(lambda: loader(*arguments))
        self.assertTrue(self.started.wait(timeout=5))
        with self.assertRaisesRegex(TimeoutError, "waiting for warehouse cache"):
            loader(*arguments)
        self.assertEqual(self.count.value, 1)
        self.assertIsNone(revenue_kpis.cache.get(loader.make_cache_key(*arguments)))
        worker.terminate()
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        result = loader(*arguments)
        self.assertEqual(self.count.value, 2)
        self.assertEqual(loader(*arguments), result)
        self.assertEqual(self.count.value, 2)

    def test_distinct_noncolliding_keys_make_independent_progress(self):
        loader = revenue_kpis.load_revenue_kpis
        first = ("test-project", "analytics")
        first_stripe = warehouse_cache.lock_stripe(loader.make_cache_key(*first))
        second = next(
            ("test-project", f"analytics_{index}")
            for index in range(100)
            if warehouse_cache.lock_stripe(
                loader.make_cache_key("test-project", f"analytics_{index}")
            )
            != first_stripe
        )
        held = self.process_context.Event()
        release = self.process_context.Event()

        def hold():
            with warehouse_cache.query_lock(loader.make_cache_key(*first)):
                held.set()
                release.wait(timeout=5)

        holder = self.start(hold)
        self.assertTrue(held.wait(timeout=5))
        follower = self.start(lambda: loader(*second))
        self.joined(follower)
        self.assertEqual(self.count.value, 1)
        release.set()
        self.joined(holder)

    def test_derived_comparison_cannot_deadlock_even_when_every_stripe_collides(self):
        with patch("warehouse_cache.lock_stripe", return_value=0):
            loader = wholesale_kpis.load_wholesale_comparison
            arguments = coverage.CacheCoverageTests.arguments(loader)
            self.concurrent(loader, arguments)
            self.assertEqual(self.count.value, 3)
            self.assertEqual(
                len(list(Path(self.directory.name).glob("query-*.lock"))), 1
            )

    def test_lock_file_count_is_bounded_and_files_private(self):
        for index in range(200):
            with warehouse_cache.query_lock(str(index)):
                pass
        files = list(Path(self.directory.name).glob("query-*.lock"))
        self.assertLessEqual(len(files), warehouse_cache.LOCK_STRIPES)
        self.assertTrue(all(path.stat().st_mode & 0o077 == 0 for path in files))


if __name__ == "__main__":
    unittest.main()
