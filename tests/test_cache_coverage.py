"""Exercise production memoized loaders with an isolated real cache, offline."""

import inspect
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
import customer_kpis
import growth_kpis
import revenue_kpis
import wholesale_kpis

MODULES = (revenue_kpis, customer_kpis, growth_kpis, wholesale_kpis)
LOADERS = (
    revenue_kpis.load_revenue_kpis,
    revenue_kpis.load_filter_catalog,
    revenue_kpis._load_executive_report,
    customer_kpis.load_customer_scorecards,
    customer_kpis.load_customer_demographics,
    customer_kpis.load_customer_map,
    customer_kpis.load_customer_lifecycle,
    customer_kpis.load_customer_segment_revenue,
    customer_kpis.load_customer_ledger,
    growth_kpis.load_growth_scorecards,
    growth_kpis.load_day_type_sales,
    growth_kpis.load_seasonality_matrix,
    growth_kpis.load_growth_ledger,
    wholesale_kpis.load_active_accounts,
    wholesale_kpis.load_reseller_revenue,
    wholesale_kpis.load_wholesale_orders,
    wholesale_kpis.load_wholesale_comparison,
    wholesale_kpis.load_top_resellers,
    wholesale_kpis.load_reseller_scatter,
    wholesale_kpis.load_wholesale_product_mix,
    wholesale_kpis.load_wholesale_operations,
)
CHANGES = {
    "project": "other-project",
    "dataset": "other_analytics",
    "staging_dataset": "other_staging",
    "dimension": "occupation",
    "year": 2025,
    "quarter": "Q2",
    "channel": "Reseller",
    "category": "Bikes",
    "subcategory": "Road Bikes",
}


class CacheCoverageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.server = Flask(__name__)
        self.server.extensions["executive_query_lock_dir"] = Path(self.directory.name)
        revenue_kpis.cache.init_app(
            self.server,
            config={
                "CACHE_TYPE": "FileSystemCache",
                "CACHE_DIR": str(Path(self.directory.name) / "cache"),
                "CACHE_THRESHOLD": 500,
            },
        )
        context = self.server.app_context()
        context.push()
        self.addCleanup(context.pop)
        self.addCleanup(revenue_kpis.cache.clear)
        self.client_patch = patch("google.cloud.bigquery.Client")
        factory = self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.client = factory.return_value.__enter__.return_value
        self.client.query.side_effect = self.query
        self.query_count = 0
        self.queries = []

    def query(self, sql, *, job_config):
        # A new warehouse response per query makes stale cache reuse observable.
        self.query_count += 1
        self.queries.append((sql, job_config))
        marker = self.query_count
        row = {
            "query_marker": marker,
            "source_rows": 1,
            "monthly": [],
            "active_accounts": marker,
            "wholesale_orders": marker,
            "total_reseller_revenue": marker,
        }
        job = Mock()
        job.result.return_value = [row]
        return job

    @staticmethod
    def arguments(loader):
        result = {}
        for name in inspect.signature(loader).parameters:
            if name == "project":
                result[name] = "test-project"
            elif name == "dataset":
                result[name] = "analytics"
            elif name == "staging_dataset":
                result[name] = "staging"
            elif name == "dimension":
                result[name] = "income"
            else:
                result[name] = None
        return result

    def test_every_memoized_loader_is_in_coverage_inventory(self):
        discovered = {
            value
            for module in MODULES
            for value in vars(module).values()
            if callable(value)
            and hasattr(value, "make_cache_key")
            and value.__module__ == module.__name__
        }
        self.assertEqual(discovered, set(LOADERS))

    def test_each_query_input_misses_and_identical_inputs_hit(self):
        for loader in LOADERS:
            with self.subTest(loader=loader.__name__):
                revenue_kpis.cache.clear()
                arguments = self.arguments(loader)
                before = self.query_count
                baseline = loader(**arguments)
                self.assertGreater(self.query_count, before)
                after = self.query_count
                self.assertEqual(loader(**arguments), baseline)
                self.assertEqual(self.query_count, after)
                for name in arguments:
                    with self.subTest(parameter=name):
                        changed = {**arguments, name: CHANGES[name]}
                        before = self.query_count
                        result = loader(**changed)
                        self.assertGreater(self.query_count, before)
                        self.assertNotEqual(result, baseline)
                        after = self.query_count
                        self.assertEqual(loader(**changed), result)
                        self.assertEqual(loader(**arguments), baseline)
                        self.assertEqual(self.query_count, after)
                        if name in {"project", "dataset", "staging_dataset"}:
                            self.assertIn(CHANGES[name], self.queries[-1][0])
                        elif name == "dimension":
                            self.assertIn("c.occupation", self.queries[-1][0])
                        else:
                            parameters = {
                                parameter.name: parameter.value
                                for parameter in self.queries[-1][1].query_parameters
                            }
                            self.assertEqual(parameters[name], CHANGES[name])

    def test_positional_keyword_and_default_calls_share_entries(self):
        for loader in LOADERS:
            with self.subTest(loader=loader.__name__):
                revenue_kpis.cache.clear()
                arguments = self.arguments(loader)
                result = loader(*arguments.values())
                after = self.query_count
                self.assertEqual(loader(**arguments), result)
                required = {
                    name: arguments[name]
                    for name, parameter in inspect.signature(loader).parameters.items()
                    if parameter.default is inspect.Parameter.empty
                }
                self.assertEqual(loader(**required), result)
                self.assertEqual(self.query_count, after)

    def test_function_names_separate_identical_argument_sets(self):
        arguments = self.arguments(customer_kpis.load_customer_demographics)
        customer_kpis.load_customer_demographics(**arguments)
        after = self.query_count
        growth_kpis.load_day_type_sales(**arguments)
        self.assertEqual(self.query_count, after + 1)

    def test_executive_public_lock_wrapper_preserves_cache_scope(self):
        loader = revenue_kpis.load_executive_report
        arguments = self.arguments(loader)
        baseline = loader(**arguments)
        after = self.query_count
        self.assertEqual(loader(*arguments.values()), baseline)
        self.assertEqual(self.query_count, after)
        for name in arguments:
            with self.subTest(parameter=name):
                before = self.query_count
                self.assertNotEqual(
                    loader(**{**arguments, name: CHANGES[name]}), baseline
                )
                self.assertEqual(self.query_count, before + 1)
                self.assertEqual(loader(**arguments), baseline)
                self.assertEqual(self.query_count, before + 1)


if __name__ == "__main__":
    unittest.main()
