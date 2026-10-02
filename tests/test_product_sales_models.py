"""Offline SQL regression checks; BigQuery deployment is tested separately."""

import sqlite3
import unittest
from pathlib import Path
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1] / "adventureworks_analytics"


class ProductSalesTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.create_function("concat", -1, lambda *xs: "".join(map(str, xs)))
        self.env = Environment()
        self.env.globals.update(ref=lambda name: name, config=lambda **kwargs: "")
        self.db.executescript("""
        create table fct_sales (product_key integer, sales_channel text,
            sales_order_number text, sales_order_line_item integer,
            order_date_key integer, order_quantity integer,
            sales_amount real, total_product_cost real);
        create table dim_product (product_key integer, category_name text,
            subcategory_name text, product_name text, model_name text,
            color text, size text, product_line text, class text, style text);
        create table dim_date (date_key integer, calendar_year integer,
            calendar_quarter_name text, month_name text);
        insert into dim_date values (20260101,2026,'Q1','January');
        insert into dim_product values
            (1,'Bikes','Road','Bike',null,'Red','M','Road','High','Universal'),
            (2,'Bikes','Road','Bike',null,'Red','M','Road','High','Universal');
        insert into fct_sales values
            (1,'Internet','SO1',1,20260101,1,100,60),
            (1,'Internet','SO1',2,20260101,1,50,20),
            (2,'Internet','SO1',3,20260101,1,25,10),
            (99,'Internet','SO2',1,20260101,1,12.3456,4.1234),
            (100,'Internet','SO3',1,20260101,1,8,3),
            (1,'Reseller','SO1',1,20260101,1,0,5);
        """)
        for folder, name in (
            ("intermediate", "int_product_sales"),
            ("marts", "marts_product_sales_performance"),
            ("marts", "revenue_sales_performance"),
        ):
            sql = self.env.from_string(
                (ROOT / "models" / folder / f"{name}.sql").read_text()
            ).render()
            self.db.execute(f"create table {name} as " + sql)

    def test_unmatched_sales_precision_versions_and_order_grains(self):
        rows = self.db.execute(
            "select product_key, product_purchasing_orders_count, gross_sales_revenue from marts_product_sales_performance where sales_channel='Internet'"
        ).fetchall()
        self.assertEqual(rows, [(1, 1, 150), (2, 1, 25), (99, 1, 12.3456), (100, 1, 8)])
        self.assertEqual(
            self.db.execute(
                "select product_name, category_name from marts_product_sales_performance where product_key=99"
            ).fetchone(),
            ("Unknown product 99", "Unknown"),
        )
        self.assertEqual(
            self.db.execute(
                "select product_purchasing_orders_count, gross_revenue_amount from revenue_sales_performance where product_name='Bike' and sales_channel='Internet'"
            ).fetchone(),
            (1, 175),
        )
        self.assertIsNone(
            self.db.execute(
                "select realized_profit_margin_percentage from marts_product_sales_performance where sales_channel='Reseller'"
            ).fetchone()[0]
        )
        self.assertAlmostEqual(
            self.db.execute(
                "select sum(gross_sales_revenue) from marts_product_sales_performance"
            ).fetchone()[0],
            195.3456,
        )

    def test_reconciliation_detects_lost_sales_and_changed_totals(self):
        src = (ROOT / "tests/generic/test_product_sales_matches_fact.sql").read_text()
        src = src.replace("{% test product_sales_matches_fact(model) %}", "").replace(
            "{% endtest %}", ""
        )
        sql = (
            self.env.from_string(src)
            .render(model="marts_product_sales_performance")
            .replace("except distinct", "except")
        )
        self.assertEqual(self.db.execute(sql).fetchall(), [])
        self.db.execute(
            "update marts_product_sales_performance set gross_sales_revenue=0 where product_key=99"
        )
        self.assertTrue(self.db.execute(sql).fetchall())
        self.db.execute(
            "delete from marts_product_sales_performance where product_key=99"
        )
        self.assertTrue(self.db.execute(sql).fetchall())


if __name__ == "__main__":
    unittest.main()
