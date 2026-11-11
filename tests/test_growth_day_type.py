import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app as app  # Initializes Dash page/callback registration.
from growth_kpis import day_type_sales_sql
from pages.growth import day_type_figure, populate_primary
from test_wholesale_kpis import ALL, CATALOG
from test_growth_filters import report
from warehouse_fixture import connect


class DayTypeTests(unittest.TestCase):
    def test_sql_grain_and_filters(self):
        db = connect("""
        CREATE TABLE fct_sales(order_date_key INTEGER,product_key INTEGER,sales_channel VARCHAR,sales_amount DOUBLE);
        CREATE TABLE dim_date(date_key INTEGER,calendar_year INTEGER,calendar_quarter_name VARCHAR,month_number INTEGER,is_weekend_flag BOOLEAN);
        CREATE TABLE dim_product(product_key INTEGER,category_name VARCHAR,subcategory_name VARCHAR);
        INSERT INTO dim_date VALUES(1,2026,'Q1',1,FALSE),(2,2026,'Q1',1,TRUE),(3,2025,'Q2',4,TRUE);
        INSERT INTO dim_product VALUES(1,'Bikes','Road Bikes'),(2,'Clothing','Jerseys');
        INSERT INTO fct_sales VALUES(1,1,'Reseller',10),(1,1,'Reseller',20),(2,1,'Internet',40),(3,2,'Reseller',50);
        """)
        self.addCleanup(db.close)
        sql = day_type_sales_sql("p", "d")
        params = dict.fromkeys(
            ("year", "quarter", "channel", "category", "subcategory")
        )
        self.assertEqual(
            db.execute(sql, params).fetchall(),
            [(2025, 4, True, 50), (2026, 1, False, 30), (2026, 1, True, 40)],
        )
        for f in (
            {"year": 2026},
            {"quarter": "Q1"},
            {"category": "Bikes"},
            {"subcategory": "Road Bikes"},
        ):
            self.assertEqual(len(db.execute(sql, {**params, **f}).fetchall()), 2)
        self.assertEqual(
            db.execute(
                sql,
                {
                    **params,
                    "year": 2026,
                    "channel": "Reseller",
                    "category": "Bikes",
                    "subcategory": "Road Bikes",
                },
            ).fetchall(),
            [(2026, 1, False, 30)],
        )

    def test_grouped_bars_and_switch(self):
        rows = [
            dict(calendar_year=2026, month_number=1, is_weekend_flag=True, revenue=40)
        ]
        fig = day_type_figure(rows)
        self.assertEqual(fig.layout.barmode, "group")
        self.assertEqual([t.name for t in fig.data], ["Weekday", "Weekend"])
        self.assertEqual(list(fig.data[0].y), [0])
        self.assertEqual(list(fig.data[1].y), [40])
        with (
            patch("pages.growth.load_filter_catalog", return_value=CATALOG),
            patch("pages.growth.load_day_type_sales", return_value=rows) as daily,
            patch(
                "pages.growth.load_executive_report",
                return_value=report([(2026, "January", 40)]),
            ) as monthly,
        ):
            result = populate_primary(
                "day-type", CATALOG, 2026, "Q1", "Reseller", "Bikes", "Road Bikes"
            )
            self.assertEqual(result[1], "Weekend Vs. Weekday Sales Volume")
            self.assertEqual(
                daily.call_args.args[2:],
                (2026, "Q1", "Reseller", "Bikes", "Road Bikes"),
            )
            monthly.assert_not_called()
            daily.reset_mock()
            self.assertEqual(
                populate_primary("line", CATALOG, *([ALL] * 5))[0].data[0].type,
                "scatter",
            )
            daily.assert_not_called()
            daily.side_effect = RuntimeError("private")
            self.assertIn(
                "Unable", populate_primary("day-type", CATALOG, *([ALL] * 5))[2]
            )
        self.assertIn("No sales", day_type_figure([]).layout.annotations[0].text)
