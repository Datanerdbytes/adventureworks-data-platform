"""Offline regression checks for portable SQL logic; no warehouse connections."""

import sqlite3
import unittest
from pathlib import Path

from jinja2 import Environment

MARTS = Path(__file__).resolve().parents[1] / "adventureworks_analytics/models/marts"


class DemographicsModelsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript("""
            create table stg_fact_internet_sales (
                sales_order_number text, sales_order_line_item integer,
                product_key integer, order_date_key integer,
                sales_territory_key integer, customer_key integer,
                order_quantity integer, sales_amount real, total_product_cost real
            );
            create table stg_fact_reseller_sales (
                sales_order_number text, sales_order_line_item integer,
                product_key integer, order_date_key integer,
                sales_territory_key integer, reseller_key integer,
                order_quantity integer, sales_amount real, total_product_cost real
            );
            create table dim_customer (
                customer_key integer, state_province_name text, city text,
                occupation text, education_level text, gender text, yearly_income real
            );
            create table dim_sales_territory (
                sales_territory_key integer, territory_group text,
                territory_country text, territory_region text
            );
            insert into dim_sales_territory values
                (1, 'Europe', 'France', 'France'),
                (2, 'Europe', 'Germany', 'Germany');
            """)

    def materialize(self):
        for name in ("fct_sales", "marts_demographic_regional_insights"):
            sql = Environment().from_string((MARTS / f"{name}.sql").read_text())
            self.db.execute(
                f"create table {name} as " + sql.render(ref=lambda model: model)
            )

    def test_channel_territories_and_unknown_demographics(self):
        self.db.executescript("""
            insert into dim_customer values (1, null, ' ', '', null, null, null);
            insert into stg_fact_internet_sales values
                ('SO1', 1, 10, 20260101, 1, 1, 1, 100, 60),
                ('SO1', 2, 11, 20260101, 1, 1, 2, 50, 20),
                ('SO2', 1, 10, 20260101, 1, 999, 1, 25, 10);
            insert into stg_fact_reseller_sales values
                ('SO1', 1, 10, 20260101, 2, 5, 3, 200, 120);
            """)
        self.materialize()
        territories = self.db.execute(
            "select distinct sales_channel, sales_territory_key from fct_sales"
        )
        self.assertEqual(
            {tuple(row) for row in territories}, {("Internet", 1), ("Reseller", 2)}
        )
        rows = {
            row["sales_channel"]: row
            for row in self.db.execute(
                "select * from marts_demographic_regional_insights"
            )
        }
        internet, reseller = rows["Internet"], rows["Reseller"]
        for field in (
            "customer_state_province",
            "customer_city",
            "customer_occupation",
            "customer_education_level",
            "customer_gender",
            "customer_income_bracket",
        ):
            self.assertEqual(internet[field], "Unknown")
            self.assertEqual(
                reseller[field],
                (
                    "Wholesale/Reseller"
                    if field in ("customer_state_province", "customer_city")
                    else "N/A - Wholesale"
                ),
            )
        self.assertEqual(internet["territory_country"], "France")
        self.assertEqual(reseller["territory_country"], "Germany")
        self.assertEqual(internet["total_orders_count"], 2)
        self.assertEqual(internet["total_units_sold"], 4)
        self.assertEqual(internet["gross_revenue_amount"], 175)
        self.assertEqual(internet["gross_profit_amount"], 85)

    def test_known_attributes_and_income_boundaries(self):
        incomes = [29999, 30000, 69999, 70000, 99999, 100000]
        for key, income in enumerate(incomes, 1):
            self.db.execute(
                "insert into dim_customer values (?, 'State', 'City', "
                "'Professional', 'Bachelors', 'Female', ?)",
                (key, income),
            )
            self.db.execute(
                "insert into stg_fact_internet_sales values "
                "(?, 1, 10, 20260101, 1, ?, 1, 100, 60)",
                (str(key), key),
            )
        self.materialize()
        rows = self.db.execute(
            "select * from marts_demographic_regional_insights"
        ).fetchall()
        self.assertEqual(
            {r["customer_income_bracket"]: r["total_orders_count"] for r in rows},
            {
                "Low Income (<30k)": 1,
                "Middle Income (30k-70k)": 2,
                "High Income (70k-100k)": 2,
                "Very High Income (100k+)": 1,
            },
        )
        self.assertTrue(all(r["customer_gender"] == "Female" for r in rows))
        self.assertTrue(all(r["customer_occupation"] == "Professional" for r in rows))


if __name__ == "__main__":
    unittest.main()
