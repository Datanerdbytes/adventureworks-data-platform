"""Offline SQL identifier and authenticated transport boundary regressions."""

import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
import customer_kpis
import growth_kpis
import revenue_kpis
import wholesale_kpis
from governance import GovernanceError, SupabaseGateway, _NoRedirect, urlopen


class WarehouseBoundaryTests(unittest.TestCase):
    def setUp(self):
        context = app.server.app_context()
        context.push()
        self.addCleanup(context.pop)

    def functions(self):
        for module in (revenue_kpis, customer_kpis, growth_kpis, wholesale_kpis):
            for name, function in inspect.getmembers(module, inspect.isfunction):
                parameters = list(inspect.signature(function).parameters)
                if parameters[:2] == ["project", "dataset"]:
                    kwargs = {}
                    if "dimension" in parameters:
                        kwargs["dimension"] = "income"
                    if "staging_dataset" in parameters:
                        kwargs["staging_dataset"] = "silver_adventureworks"
                    for parameter in inspect.signature(function).parameters.values():
                        if (
                            parameter.name not in {"project", "dataset"}
                            and parameter.name not in kwargs
                            and parameter.default is inspect.Parameter.empty
                        ):
                            kwargs[parameter.name] = None
                    yield name, function, kwargs

    def test_all_builders_and_loaders_reject_identifier_injection_before_clients(self):
        for name, function, kwargs in self.functions():
            for project, dataset in (
                ("bad`project", "safe_dataset"),
                ("test-project", "bad`dataset"),
                (None, "safe_dataset"),
            ):
                with (
                    self.subTest(function=name, project=project, dataset=dataset),
                    patch("google.cloud.bigquery.Client") as client,
                ):
                    with self.assertRaises(ValueError):
                        function(project, dataset, **kwargs)
                    client.assert_not_called()

    def test_staging_dataset_is_guarded_on_builder_and_loader(self):
        for function in (
            wholesale_kpis.wholesale_operations_sql,
            wholesale_kpis.load_wholesale_operations,
        ):
            with (
                self.subTest(function=function.__name__),
                patch("google.cloud.bigquery.Client") as client,
            ):
                with self.assertRaises(ValueError):
                    function("test-project", "gold_adventureworks", "silver`; SELECT 1")
                client.assert_not_called()

    def test_customer_dimension_remains_server_allowlisted(self):
        with self.assertRaises(KeyError):
            customer_kpis.customer_segment_revenue_sql(
                "test-project", "safe_dataset", "occupation); SELECT 1"
            )

    def test_hostile_filter_values_are_bound_without_changing_sql(self):
        marker = "Bikes' OR 1=1 --"
        expected = revenue_kpis.executive_sql("test-project", "safe_dataset")
        row = {"source_rows": 1, "gross_revenue_amount": 1}
        client = MagicMock()
        client.query.return_value.result.return_value = [row]
        with patch("google.cloud.bigquery.Client") as factory:
            factory.return_value.__enter__.return_value = client
            # Execute the uncached loader to inspect the actual job configuration.
            revenue_kpis._load_executive_report.__wrapped__(
                "test-project", "safe_dataset", category=marker
            )
        args = client.query.call_args
        self.assertEqual(args.args[0], expected)
        self.assertNotIn(marker, args.args[0])
        parameters = {p.name: p for p in args.kwargs["job_config"].query_parameters}
        self.assertEqual(parameters["category"].value, marker)
        self.assertEqual(parameters["category"].type_, "STRING")


class GovernanceTransportTests(unittest.TestCase):
    def test_unsupported_urls_are_rejected_before_transport(self):
        for url in (
            "file:///etc/passwd",
            "http://example.test",
            "ftp://example.test",
            "https://user:password@example.test",  # pragma: allowlist secret (synthetic fixture)
            "https://example.test/base",
            "https://example.test?query=1",
            "https://example.test#fragment",
            "https://example.test:invalid",
            "https://example.test\n",
        ):
            with self.subTest(url=url), patch("governance.build_opener") as opener:
                with self.assertRaises(GovernanceError):
                    SupabaseGateway(url, "public", "fixture-token")
                opener.assert_not_called()

    def test_https_and_explicit_local_http_remain_supported(self):
        for url in (
            "https://project.supabase.co",
            "http://localhost:54321",
            "http://127.0.0.1:54321",
            "http://[::1]:54321",
        ):
            self.assertEqual(SupabaseGateway(url, "public", None).url, url)

    def test_absolute_and_network_paths_fail_before_transport(self):
        client = SupabaseGateway(
            "https://project.supabase.co", "public", "fixture-token"
        )
        for path in (
            "https://elsewhere.test/auth",
            "//elsewhere.test/auth",
            "/auth#fragment",
            "/auth\n",
        ):
            with self.subTest(path=path), patch("governance.urlopen") as transport:
                with self.assertRaises(GovernanceError):
                    client.request(path)
                transport.assert_not_called()

    def test_redirects_cannot_forward_credentials(self):
        handler = _NoRedirect()
        request = Request(
            "https://project.supabase.co/auth/v1/user",
            headers={
                "Authorization": "Bearer fixture-token",  # pragma: allowlist secret (synthetic fixture)
                "apikey": "public",  # pragma: allowlist secret (public fixture)
            },
        )
        for code in (301, 302, 303, 307, 308):
            self.assertIsNone(
                handler.redirect_request(
                    request, None, code, "Redirect", {}, "https://elsewhere.test"
                )
            )
        with patch("governance.build_opener") as build:
            urlopen(request, timeout=8)
        self.assertIsInstance(build.call_args.args[0], _NoRedirect)
        build.return_value.open.assert_called_once_with(request, timeout=8)

    def test_transport_itself_rejects_unsafe_schemes(self):
        with patch("governance.build_opener") as opener:
            with self.assertRaises(GovernanceError):
                urlopen(Request("file:///etc/passwd"), timeout=8)
            opener.assert_not_called()
