import re
import sqlite3
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from growth_kpis import growth_ledger_sql
from pages.growth import (
    populate_growth,
    detail_columns,
    export_growth_ledger,
    ledger_card,
)
from test_wholesale_kpis import ALL, CATALOG


class LedgerTests(unittest.TestCase):
    def test_order_grain_split_and_prior_month(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.create_function("SAFE_DIVIDE", 2, lambda a, b: a / b if b else None)
        db.executescript("""
        CREATE TABLE fct_sales(order_date_key,product_key,sales_channel,sales_order_number,sales_amount);
        CREATE TABLE dim_date(date_key,calendar_date,is_weekend_flag);
        CREATE TABLE dim_product(product_key,category_name,subcategory_name);
        INSERT INTO dim_date VALUES(1,'2025-12-01',0),(2,'2026-01-01',0),(3,'2026-01-03',1),(4,'2026-03-01',1);
        INSERT INTO dim_product VALUES(1,'Bikes','Road Bikes'),(2,'Clothing','Jerseys');
        INSERT INTO fct_sales VALUES(1,1,'Reseller','a',100),(2,1,'Reseller','b',20),(2,1,'Reseller','b',30),(3,1,'Internet','b',150),(4,2,'Internet','c',80);
        """)
        sql = re.sub(r"`p.d.(\w+)`", r"\1", growth_ledger_sql("p", "d"))
        sql = (
            sql.replace(
                "DATE_TRUNC(d.calendar_date, MONTH)",
                "date(d.calendar_date, 'start of month')",
            )
            .replace(
                "COUNTIF(sales_order_number IS NOT NULL)",
                "SUM(sales_order_number IS NOT NULL)",
            )
            .replace("DATE_SUB(month, INTERVAL 1 MONTH)", "date(month,'-1 month')")
            .replace(
                "EXTRACT(YEAR FROM month)", "CAST(strftime('%Y',month) AS INTEGER)"
            )
            .replace(
                "CONCAT('Q', CAST(EXTRACT(QUARTER FROM month) AS STRING))",
                "'Q' || CAST((CAST(strftime('%m',month) AS INTEGER)+2)/3 AS INTEGER)",
            )
        )
        params = dict(
            year=2026, quarter=None, channel=None, category=None, subcategory=None
        )
        rows = db.execute(sql, params).fetchall()
        self.assertEqual(rows[0], ("2026-01-01", 200, 2, 50, 150, 75, 100))
        self.assertIsNone(rows[1][-1])
        filtered = db.execute(
            sql,
            {
                **params,
                "quarter": "Q1",
                "channel": "Reseller",
                "category": "Bikes",
                "subcategory": "Road Bikes",
            },
        ).fetchall()
        self.assertEqual(filtered, [("2026-01-01", 50, 1, 50, 0, 0, -50)])

    def test_numeric_rows_sorting_export_and_pagination(self):
        row = dict(
            month=date(2026, 1, 1),
            revenue=200,
            orders=2,
            weekday_revenue=50,
            weekend_revenue=150,
            weekend_share=75,
            mom_growth=100,
        )
        with (
            patch("pages.growth.load_filter_catalog", return_value=CATALOG),
            patch("pages.growth.load_growth_ledger", return_value=[row]),
        ):
            rows, columns, options, _ = populate_growth(CATALOG, *([ALL] * 5), {})
        self.assertEqual(options["paginationPageSize"], 12)
        self.assertTrue(options["pagination"])
        self.assertEqual(rows[0]["period"], "2026-01")
        self.assertEqual(rows[0]["revenue"], 200)
        self.assertEqual(
            [c["headerName"] for c in columns],
            [
                "Time Period",
                "Total Gross Revenue",
                "Order Volume Baseline",
                "Weekday Sales Volume",
                "Weekend Sales Volume",
                "Weekend Vol % Split",
                "MoM Growth %",
            ],
        )
        self.assertEqual(columns[0]["sort"], "asc")
        self.assertTrue(all(c["useValueFormatterForExport"] is False for c in columns))
        self.assertTrue(export_growth_ledger(1))
        table = ledger_card().children[-1].children
        self.assertTrue(table.defaultColDef["sortable"])
        self.assertEqual(
            table.csvExportParams["fileName"], "growth-seasonality-pacing-ledger.csv"
        )
