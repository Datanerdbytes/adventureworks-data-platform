import calendar
from datetime import date
from pathlib import Path
import re
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from customer_kpis import customer_scorecards_sql
from pages.customers import populate_scorecards, render_scorecards
from test_wholesale_kpis import ALL, CATALOG
from dash.exceptions import PreventUpdate


class CustomerKpiTests(unittest.TestCase):
    def test_customer_cohort_churn_and_state_invoice_grain(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.create_function("IF", 3, lambda condition, yes, no: yes if condition else no)
        db.create_function(
            "DATE_DIFF",
            3,
            lambda end, start, unit: (
                date.fromisoformat(end) - date.fromisoformat(start)
            ).days,
        )

        def last_day(value, unit):
            if value is None:
                return None
            d = date.fromisoformat(value)
            month = 12 if unit == "YEAR" else ((d.month - 1) // 3 + 1) * 3
            return date(
                d.year, month, calendar.monthrange(d.year, month)[1]
            ).isoformat()

        db.create_function("LAST_DAY", 2, last_day)
        db.executescript("""
        CREATE TABLE fct_sales(customer_key,sales_channel,sales_order_number,order_date_key,sales_amount,product_key,sales_territory_key);
        CREATE TABLE dim_date(date_key,calendar_date,calendar_year,calendar_quarter_name);
        CREATE TABLE dim_customer(customer_key,state_province_name,country_region_name,date_first_purchase);
        CREATE TABLE dim_product(product_key,category_name,subcategory_name);
        CREATE TABLE dim_sales_territory(sales_territory_key,territory_group);
        INSERT INTO dim_date VALUES(0,'2025-12-01',2025,'Q4'),(1,'2026-01-01',2026,'Q1'),(2,'2026-01-03',2026,'Q1'),(3,'2026-06-30',2026,'Q2'),(4,'2026-07-02',2026,'Q3');
        INSERT INTO dim_customer VALUES(1,'California','US',NULL),(2,'California','US',NULL),(3,'California','US',NULL),(4,'California','US',NULL),(5,'California','US',NULL);
        INSERT INTO dim_product VALUES(1,'Bikes','Road Bikes'),(2,'Clothing','Jerseys');
        INSERT INTO dim_sales_territory VALUES(1,'North America');
        INSERT INTO fct_sales VALUES(4,'Internet','old',0,100,1,1),(1,'Internet','a',1,20,1,1),(1,'Internet','a',1,30,1,1),(2,'Internet','b',1,50,1,1),(3,'Internet','c',2,50,1,1),(1,'Internet','d',3,40,2,1),(5,'Internet','e',4,10,1,1),(5,'Internet','e',4,10,1,1),(5,'Internet','f',4,10,1,1),(NULL,'Reseller','a',4,900,1,1);
        """)
        sql = customer_scorecards_sql("p", "d").split(
            "SELECT (SELECT COUNT(*) FROM selected)"
        )[0]
        sql = re.sub(r"`p.d.(\w+)`", r"\1", sql)
        sql = (
            sql.replace("LEAST(", "MIN(")
            .replace(
                "LAST_DAY(latest_selected, QUARTER)",
                "LAST_DAY(latest_selected, 'QUARTER')",
            )
            .replace(
                "LAST_DAY(latest_selected, YEAR)", "LAST_DAY(latest_selected, 'YEAR')"
            )
        )
        sql = sql.replace(
            "DATE_TRUNC(order_date, MONTH)", "date(order_date,'start of month')"
        ).replace("DATE_TRUNC(as_of, MONTH)", "date(as_of,'start of month')")
        sql = sql.replace(
            "DATE_SUB(date(as_of,'start of month'), INTERVAL 1 MONTH)",
            "date(as_of,'start of month','-1 month')",
        )
        params = dict(
            year=2026, quarter=None, channel=None, category="Bikes", subcategory=None
        )
        self.assertEqual(
            db.execute(sql + "SELECT COUNT(*) FROM cohort", params).fetchone()[0], 5
        )
        self.assertEqual(
            db.execute(
                sql
                + "SELECT SUM(s.sales_amount) FROM scoped s JOIN cohort c USING(customer_key) CROSS JOIN cutoff WHERE s.sales_channel='Internet' AND s.order_date <= as_of",
                params,
            ).fetchone()[0],
            280,
        )
        last = dict(
            db.execute(sql + "SELECT customer_key,last_order FROM last_orders", params)
        )
        # A later order outside the product selection prevents false customer churn.
        self.assertEqual(last[1], "2026-06-30")
        cutoff = date.fromisoformat(
            db.execute(sql + "SELECT as_of FROM cutoff", params).fetchone()[0]
        )
        self.assertEqual(
            sum((cutoff - date.fromisoformat(d)).days > 180 for d in last.values()), 2
        )
        # Duplicate invoice lines do not inflate transaction growth; prior month is outside Q3.
        params.update(quarter="Q3", category=None)
        self.assertEqual(
            db.execute(
                sql
                + "SELECT current_orders,previous_orders,increase FROM state_growth",
                params,
            ).fetchone(),
            (2, 1, 1),
        )
        params["channel"] = "Reseller"
        self.assertEqual(
            db.execute(sql + "SELECT COUNT(*) FROM cohort", params).fetchone()[0], 0
        )

    def test_filters_states_and_values(self):
        data = dict(
            customers=4,
            customer_revenue=200,
            dormant=1,
            as_of=date(2026, 7, 2),
            matching_rows=8,
            top_territory=dict(territory="North America", revenue=1100),
            top_state=None,
        )
        cards = render_scorecards(data)
        self.assertEqual(cards[1].children[1].children, "$50.00")
        self.assertEqual(cards[4].children[1].children, "25.00%")
        self.assertEqual(
            render_scorecards(data, "Reseller")[0].children[2].children,
            "Not applicable",
        )
        empty = {
            **data,
            "customers": 0,
            "customer_revenue": None,
            "dormant": 0,
            "top_territory": None,
            "matching_rows": 0,
        }
        self.assertEqual(render_scorecards(empty)[0].children[1].children, "0")
        self.assertEqual(render_scorecards(empty)[1].children[1].children, "—")
        self.assertEqual(
            render_scorecards(data)[3].children[2].children, "Baseline unavailable"
        )
        self.assertEqual(
            render_scorecards({**data, "state_baseline_available": True})[3]
            .children[2]
            .children,
            "No growth",
        )
        with (
            patch("pages.customers.load_filter_catalog", return_value=CATALOG),
            patch(
                "pages.customers.load_customer_scorecards", return_value=data
            ) as loader,
        ):
            for values in ([ALL] * 5, [2026, "Q1", "Reseller", "Bikes", "Road Bikes"]):
                populate_scorecards(CATALOG, *values)
                self.assertEqual(
                    loader.call_args.args[2:],
                    tuple(None if v == ALL else v for v in values),
                )
            with self.assertRaises(PreventUpdate):
                populate_scorecards(CATALOG, ALL, ALL, ALL, "Clothing", "Road Bikes")
            loader.side_effect = RuntimeError("private details")
            result = populate_scorecards(CATALOG, *([ALL] * 5))
            self.assertIn("Unable to load", result[-1])
            self.assertNotIn("private", str(result))
        self.assertIn("Waiting", populate_scorecards(None, *([ALL] * 5))[-1])
