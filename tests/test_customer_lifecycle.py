import re
import sqlite3
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from test_customer_kpis import app, CATALOG, ALL
from customer_kpis import customer_lifecycle_sql
from pages.customers import lifecycle_figure, populate_customer_chart, LIFECYCLE_STAGES
from dash.exceptions import PreventUpdate


class LifecycleTests(unittest.TestCase):
    def test_history_boundaries_and_distinct_invoices(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.create_function(
            "DATE_DIFF",
            3,
            lambda a, b, unit: (date.fromisoformat(a) - date.fromisoformat(b)).days,
        )
        db.create_function("LAST_DAY", 2, lambda value, unit: value)
        db.executescript("""
          CREATE TABLE fct_sales(customer_key,sales_channel,sales_order_number,order_date_key,sales_amount,product_key,sales_territory_key);
          CREATE TABLE dim_date(date_key,calendar_date,calendar_year,calendar_quarter_name);
          CREATE TABLE dim_customer(customer_key,state_province_name,country_region_name,date_first_purchase);
          CREATE TABLE dim_product(product_key,category_name,subcategory_name);
          CREATE TABLE dim_sales_territory(sales_territory_key,territory_group);
          INSERT INTO dim_product VALUES (1,'Bikes','Road Bikes'),(2,'Clothing','Jerseys');
          INSERT INTO dim_sales_territory VALUES (1,'North America');
        """)
        cutoff = date(2026, 7, 1)
        for key, days in enumerate([0, 90, 91, 180, 181], 1):
            d = cutoff - timedelta(days=days)
            db.execute(
                "INSERT INTO dim_date VALUES (?,?,?,?)",
                (key, d.isoformat(), 2026, "Q3" if key == 1 else "Q1"),
            )
            db.execute("INSERT INTO dim_customer VALUES (?,NULL,NULL,NULL)", (key,))
            # Duplicate invoice lines must not turn a first-time buyer into a repeat buyer.
            for _ in range(2):
                db.execute(
                    'INSERT INTO fct_sales VALUES (?,"Internet",?,?,10,1,1)',
                    (key, str(key), key),
                )
        db.execute('INSERT INTO fct_sales VALUES (1,"Internet","repeat",1,10,2,1)')
        db.execute(
            "INSERT INTO dim_customer VALUES (6,NULL,NULL,?)",
            ((cutoff - timedelta(days=181)).isoformat(),),
        )
        db.execute('INSERT INTO dim_customer VALUES (7,NULL,NULL,"2027-01-01")')
        sql = re.sub(r"`p.d.(\w+)`", r"\1", customer_lifecycle_sql("p", "d"))
        sql = (
            sql.replace("LEAST(", "MIN(")
            .replace(", QUARTER)", ", 'QUARTER')")
            .replace(", YEAR)", ", 'YEAR')")
            .replace(", DAY)", ", 'DAY')")
        )
        params = dict(
            year=None, quarter=None, channel=None, category=None, subcategory=None
        )

        def counts(**changes):
            return {r[0]: r[1] for r in db.execute(sql, params | changes)}

        self.assertEqual(
            counts(),
            {"New Cohort": 1, "Active Repeat": 1, "Slipping Account": 2, "Dormant": 2},
        )
        # Product scope retains repeat activity in a different product category.
        self.assertEqual(counts(category="Bikes")["Active Repeat"], 1)
        self.assertEqual(counts(category="Bikes")["Dormant"], 1)
        # Date filter sets the cutoff; it must not erase dormant profiles.
        self.assertEqual(counts(quarter="Q3")["Dormant"], 2)
        self.assertEqual(counts(channel="Reseller"), {})

    def test_funnel_order_zero_stage_and_exact_counts(self):
        fig = lifecycle_figure(
            [dict(stage="Dormant", customers=8), dict(stage="New Cohort", customers=3)]
        )
        self.assertEqual(fig.data[0].type, "funnel")
        self.assertEqual(list(fig.data[0].y), LIFECYCLE_STAGES)
        self.assertEqual(list(fig.data[0].x), [3, 0, 0, 8])
        self.assertIn("No retail", lifecycle_figure([]).layout.annotations[0].text)

    def test_active_view_filters_and_error_states(self):
        with (
            patch("pages.customers.load_filter_catalog", return_value=CATALOG),
            patch("pages.customers.load_customer_lifecycle", return_value=[]) as loader,
            patch("pages.customers.load_customer_demographics", return_value=[]) as age,
        ):
            populate_customer_chart("funnel", CATALOG, *([ALL] * 5))
            self.assertEqual(loader.call_args.args[2:], (None,) * 5)
            age.assert_not_called()
            loader.reset_mock()
            populate_customer_chart("age", CATALOG, *([ALL] * 5))
            loader.assert_not_called()
            age.assert_called_once()
            with self.assertRaises(PreventUpdate):
                populate_customer_chart(
                    "funnel", CATALOG, ALL, ALL, ALL, "Clothing", "Road Bikes"
                )
            loader.side_effect = RuntimeError("private")
            self.assertIn(
                "Unable to load",
                populate_customer_chart("funnel", CATALOG, *([ALL] * 5))[1],
            )
        self.assertIn(
            "Waiting", populate_customer_chart("funnel", None, *([ALL] * 5))[1]
        )
