"""Report registration, aggregates, and filtering; all data is synthetic."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
import dash
from analytics import REPORTS, build_report, sales_fixture


class ReportTests(unittest.TestCase):
    def test_all_four_routes_registered(self):
        registered = {p["path"] for p in dash.page_registry.values()}
        for kind in REPORTS:
            self.assertIn(f"/dashboard/{kind}", registered)

    def test_each_report_and_region_filter(self):
        for kind in REPORTS:
            for year in (2025, 2026):
                with self.subTest(kind=kind, year=year):
                    result = build_report(kind, year, "Canada", {"pageSize": 20})
                    self.assertEqual(len(result[0]), 4)
                    self.assertTrue(len(result[1].data))
                    self.assertTrue(result[3])
                    self.assertEqual(result[5]["paginationPageSize"], 20)
                    self.assertIn("synthetic", result[6])
                    for row in result[3]:
                        if "Region" in row:
                            self.assertEqual(row["Region"], "Canada")

    def test_revenue_reconciles(self):
        fixture = sales_fixture()
        expected = fixture.loc[fixture.Year == 2026, "Revenue"].sum()
        rows = build_report("executive", 2026, "All regions")[3]
        self.assertAlmostEqual(sum(r["Revenue"] for r in rows), expected, places=2)
        wholesale = build_report("wholesale", 2026, "All regions")[3]
        expected = fixture[
            (fixture.Year == 2026) & (fixture.Channel == "Reseller")
        ].Revenue.sum()
        self.assertAlmostEqual(sum(r["Revenue"] for r in wholesale), expected, places=2)

    def test_growth_baseline_and_customers(self):
        rows = build_report("growth", 2025, "All regions")[3]
        self.assertIsNone(rows[0]["Growth (%)"])
        self.assertEqual(len(rows), 12)
        rows = build_report("growth", 2026, "All regions")[3]
        self.assertIsNotNone(rows[0]["Growth (%)"])
        customers = build_report("customers", 2026, "All regions")[3]
        fixture = sales_fixture()
        expected = fixture[
            (fixture.Year == 2026) & (fixture.Channel == "Internet")
        ].Customer.nunique()
        self.assertEqual(sum(r["Customers"] for r in customers), expected)

    def test_invalid_filters_are_empty(self):
        for kind in REPORTS:
            self.assertEqual(build_report(kind, None, "All regions")[3], [])
            self.assertEqual(build_report(kind, 2026, "Missing region")[3], [])
