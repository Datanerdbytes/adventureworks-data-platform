import unittest
import sqlite3
import re
from unittest.mock import patch
from test_customer_kpis import app, CATALOG, ALL
from customer_kpis import customer_segment_revenue_sql
from pages.customers import (
    segment_revenue_figure,
    populate_customer_chart,
    SEGMENT_TITLES,
)
from dash.exceptions import PreventUpdate


class SegmentRevenueTests(unittest.TestCase):
    def test_warehouse_aggregation_and_filters(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript("""
        CREATE TABLE fct_sales(customer_key,order_date_key,product_key,sales_channel,sales_amount);
        CREATE TABLE dim_date(date_key,calendar_year,calendar_quarter_name);
        CREATE TABLE dim_product(product_key,category_name,subcategory_name);
        CREATE TABLE dim_customer(customer_key,yearly_income,occupation,education_level);
        INSERT INTO dim_date VALUES (1,2026,'Q1'),(2,2025,'Q4');
        INSERT INTO dim_product VALUES (1,'Bikes','Road Bikes');
        INSERT INTO dim_customer VALUES (1,29999,'Professional','Graduate Degree'),(2,30000,'Manual','High School'),(3,70000,'Professional','Graduate Degree'),(4,100000,' ','');
        INSERT INTO fct_sales VALUES (1,1,1,'Internet',10),(1,1,1,'Internet',15),(2,1,1,'Internet',20),(3,1,1,'Internet',30),(4,1,1,'Internet',40),(5,1,1,'Internet',50),(NULL,1,1,'Reseller',999),(1,2,1,'Internet',100);
        """)
        params = dict(
            year=2026,
            quarter="Q1",
            channel=None,
            category="Bikes",
            subcategory="Road Bikes",
        )

        def query(dim, **changes):
            sql = re.sub(
                r"`p.d.(\w+)`", r"\1", customer_segment_revenue_sql("p", "d", dim)
            )
            return dict(db.execute(sql, params | changes))

        self.assertEqual(
            query("income"),
            {
                "Low Income (<30k)": 25,
                "Middle Income (30k-70k)": 20,
                "High Income (70k-100k)": 30,
                "Very High Income (100k+)": 40,
                "Unknown": 50,
            },
        )
        self.assertEqual(
            query("occupation"), {"Professional": 55, "Manual": 20, "Unknown": 90}
        )
        self.assertEqual(query("education")["Graduate Degree"], 55)
        self.assertEqual(query("education", channel="Reseller"), {})
        self.assertEqual(query("income", subcategory="Jerseys"), {})
        with self.assertRaises(KeyError):
            customer_segment_revenue_sql("p", "d", "untrusted")

    def test_figures_and_dispatch(self):
        rows = [
            dict(segment="Graduate Degree", revenue=1234),
            dict(segment="High School", revenue=99),
        ]
        fig = segment_revenue_figure(rows, "education")
        self.assertEqual(fig.data[0].orientation, "h")
        self.assertEqual(list(fig.data[0].y), ["Graduate Degree", "High School"])
        self.assertIn(
            "No retail", segment_revenue_figure([], "income").layout.annotations[0].text
        )
        with (
            patch("pages.customers.load_filter_catalog", return_value=CATALOG),
            patch(
                "pages.customers.load_customer_segment_revenue", return_value=rows
            ) as loader,
            patch("pages.customers.load_customer_lifecycle") as lifecycle,
            patch("pages.customers.load_customer_demographics") as demographics,
        ):
            for dimension, title in SEGMENT_TITLES.items():
                result = populate_customer_chart(dimension, CATALOG, *([ALL] * 5))
                self.assertEqual(result[2], title)
                self.assertEqual(
                    loader.call_args.args[2:], (dimension, None, None, None, None, None)
                )
            lifecycle.assert_not_called()
            demographics.assert_not_called()
            with self.assertRaises(PreventUpdate):
                populate_customer_chart(
                    "income", CATALOG, ALL, ALL, ALL, "Clothing", "Road Bikes"
                )
            loader.side_effect = RuntimeError("private")
            self.assertIn(
                "Unable to load",
                populate_customer_chart("income", CATALOG, *([ALL] * 5))[1],
            )
