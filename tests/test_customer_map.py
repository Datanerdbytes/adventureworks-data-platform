import unittest
from unittest.mock import patch
from test_customer_kpis import app, CATALOG, ALL
from customer_map import revenue_map, OVERVIEW
from pages.customers import populate_region
from customer_kpis import customer_map_sql


class CustomerMapTests(unittest.TestCase):
    def test_group_totals_drilldown_aliases_and_unlocated(self):
        rows = [
            dict(
                territory_group="Europe",
                country="France",
                state="Seine (Paris)",
                revenue=100,
            ),
            dict(
                territory_group="Europe",
                country="France",
                state="Seine (Paris)",
                revenue=50,
            ),
            dict(
                territory_group="Europe",
                country="France",
                state="Wholesale/Reseller",
                revenue=200,
            ),
            dict(
                territory_group="North America",
                country="Canada",
                state="British Columbia",
                revenue=70,
            ),
        ]
        overview, _ = revenue_map(rows)
        self.assertEqual(
            dict(zip(overview.data[0].locations, overview.data[0].z)),
            {"Europe": 350, "North America": 70},
        )
        states, note = revenue_map(rows, "Europe")
        self.assertEqual(list(states.data[0].z), [150])
        self.assertIn("$200.00", note)
        self.assertIn("Seine (Paris)", note)
        self.assertEqual(revenue_map([])[0].data, ())

    def test_active_view_only_and_filters(self):
        with (
            patch("pages.customers.load_filter_catalog", return_value=CATALOG),
            patch("pages.customers.load_customer_map", return_value=[]) as maps,
            patch(
                "pages.customers.load_customer_demographics", return_value=[]
            ) as demo,
        ):
            populate_region("bar", OVERVIEW, CATALOG, *([ALL] * 5))
            maps.assert_not_called()
            demo.assert_called_once()
            vals = [2026, "Q1", "Reseller", "Bikes", "Road Bikes"]
            result = populate_region("map", OVERVIEW, CATALOG, *vals)
            self.assertEqual(maps.call_args.args[2:], tuple(vals))
            self.assertFalse(result[2])
            demo.assert_called_once()
            maps.side_effect = RuntimeError("private")
            self.assertIn(
                "Unable to load", populate_region("map", OVERVIEW, CATALOG, *vals)[-1]
            )

    def test_sql_sources(self):
        self.assertIn("SUM(gross_revenue_amount)", customer_map_sql("p", "d", True))
        sql = customer_map_sql("p", "d")
        for name in ["year", "quarter", "channel", "category", "subcategory"]:
            self.assertIn("@" + name, sql)
        self.assertIn("'Wholesale/Reseller'", sql)
