import unittest
from unittest.mock import patch
from test_customer_kpis import app, CATALOG, ALL
from pages.customers import demographic_figures, populate_demographics, layout
from dash.exceptions import PreventUpdate


class DemographicsTests(unittest.TestCase):
    def test_aggregation_order_and_empty(self):
        rows = [
            dict(region="Canada", age_group="60+", customers=3, as_of="2014-01-28"),
            dict(region="Canada", age_group="18–29", customers=2, as_of="2014-01-28"),
            dict(region="France", age_group="18–29", customers=4, as_of="2014-01-28"),
        ]
        region, age = demographic_figures(rows)
        self.assertEqual(list(region.data[0].x), [4, 5])
        self.assertEqual(list(age.data[0].x), ["18–29", "60+"])
        self.assertEqual(list(age.data[0].y), [6, 3])
        self.assertIn(
            "No retail", demographic_figures([])[0].layout.annotations[0].text
        )

    def test_filters_and_failure_states(self):
        with (
            patch("pages.customers.load_filter_catalog", return_value=CATALOG),
            patch(
                "pages.customers.load_customer_demographics", return_value=[]
            ) as loader,
        ):
            values = [2026, "Q1", "Reseller", "Bikes", "Road Bikes"]
            populate_demographics(CATALOG, *values)
            self.assertEqual(loader.call_args.args[2:], tuple(values))
            populate_demographics(CATALOG, *([ALL] * 5))
            self.assertEqual(loader.call_args.args[2:], (None,) * 5)
            with self.assertRaises(PreventUpdate):
                populate_demographics(CATALOG, ALL, ALL, ALL, "Clothing", "Road Bikes")
            loader.side_effect = RuntimeError("private")
            self.assertIn(
                "Unable to load", populate_demographics(CATALOG, *([ALL] * 5))[-1]
            )
        self.assertIn("Waiting", populate_demographics(None, *([ALL] * 5))[-1])

    def test_sample_controls_removed(self):
        def ids(node):
            if isinstance(node, list):
                return [key for child in node for key in ids(child)]
            if not hasattr(node, "children"):
                return [node.id] if getattr(node, "id", None) else []
            return ([node.id] if getattr(node, "id", None) else []) + ids(node.children)

        identifiers = ids(layout())
        self.assertNotIn("customers-year", identifiers)
        self.assertNotIn("customers-region", identifiers)
        self.assertIn("customers-chart-status", identifiers)
