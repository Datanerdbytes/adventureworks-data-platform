import calendar
import re
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from growth_kpis import seasonality_matrix_sql
from pages.growth import seasonality_matrix_figure, populate_secondary
from test_wholesale_kpis import CATALOG, ALL
from test_growth_filters import report


class MatrixTests(unittest.TestCase):
    def test_order_gaps_and_view_switch(self):
        rows = [
            dict(month_number=2, day_name="Sunday", units=30),
            dict(month_number=1, day_name="Monday", units=10),
        ]
        figure = seasonality_matrix_figure(rows)
        self.assertEqual(list(figure.data[0].y), list(calendar.day_name))
        self.assertEqual(list(figure.data[0].x), list(calendar.month_name)[1:])
        self.assertEqual(figure.data[0].z[0][0], 10)
        self.assertEqual(figure.data[0].z[6][1], 30)
        self.assertEqual(figure.data[0].z[1][0], 0)
        self.assertIsNone(figure.data[0].z[0][2])
        self.assertEqual(figure.layout.yaxis.autorange, "reversed")
        with (
            patch("pages.growth.load_filter_catalog", return_value=CATALOG),
            patch("pages.growth.load_seasonality_matrix", return_value=rows) as matrix,
            patch(
                "pages.growth.load_executive_report",
                return_value=report([(2026, "January", 50)]),
            ) as monthly,
        ):
            result = populate_secondary(
                "matrix", CATALOG, 2026, "Q1", "Reseller", "Bikes", "Road Bikes"
            )
            self.assertEqual(result[1], "Annual Seasonality Peak Matrix")
            self.assertEqual(
                matrix.call_args.args[2:],
                (2026, "Q1", "Reseller", "Bikes", "Road Bikes"),
            )
            monthly.assert_not_called()
            matrix.reset_mock()
            self.assertEqual(
                populate_secondary("growth", CATALOG, *([ALL] * 5))[1],
                "Month-Over-Month Revenue Growth",
            )
            matrix.assert_not_called()
            matrix.side_effect = RuntimeError("private")
            self.assertIn(
                "Unable", populate_secondary("matrix", CATALOG, *([ALL] * 5))[2]
            )
        self.assertIn(
            "No sales", seasonality_matrix_figure([]).layout.annotations[0].text
        )

    def test_years_aggregate_and_filters(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript("""
        CREATE TABLE fct_sales(order_date_key,product_key,sales_channel,order_quantity);
        CREATE TABLE dim_date(date_key,calendar_year,calendar_quarter_name,month_number,day_of_week_name);
        CREATE TABLE dim_product(product_key,category_name,subcategory_name);
        INSERT INTO dim_date VALUES(1,2026,'Q1',1,'Monday'),(2,2025,'Q1',1,'Monday'),(3,2026,'Q2',4,'Sunday');
        INSERT INTO dim_product VALUES(1,'Bikes','Road Bikes'),(2,'Clothing','Jerseys');
        INSERT INTO fct_sales VALUES(1,1,'Reseller',10),(1,1,'Internet',5),(2,1,'Reseller',20),(3,2,'Reseller',40);
        """)
        sql = re.sub(r"`p.d.(\w+)`", r"\1", seasonality_matrix_sql("p", "d"))
        params = dict.fromkeys(
            ("year", "quarter", "channel", "category", "subcategory")
        )
        self.assertEqual(
            db.execute(sql, params).fetchall(), [(1, "Monday", 35), (4, "Sunday", 40)]
        )
        self.assertEqual(
            db.execute(
                sql,
                dict(
                    year=2026,
                    quarter="Q1",
                    channel="Reseller",
                    category="Bikes",
                    subcategory="Road Bikes",
                ),
            ).fetchall(),
            [(1, "Monday", 10)],
        )
        self.assertEqual(db.execute(sql, {**params, "year": 2024}).fetchall(), [])
