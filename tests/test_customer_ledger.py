import re
import sqlite3
import unittest
from datetime import date
from unittest.mock import patch
from test_customer_kpis import app, CATALOG, ALL
from customer_kpis import customer_ledger_sql
from pages.customers import (
    populate_customer_ledger,
    customer_ledger_card,
    export_customer_ledger,
)
from dash.exceptions import PreventUpdate


class CustomerLedgerTests(unittest.TestCase):
    def test_customer_weighted_modes_geography_and_order_grain(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.row_factory = sqlite3.Row
        db.create_function(
            "DATE_DIFF",
            3,
            lambda a, b, u: (date.fromisoformat(a) - date.fromisoformat(b)).days,
        )
        db.create_function("LAST_DAY", 2, lambda value, unit: value)
        db.executescript("""
        CREATE TABLE fct_sales(customer_key,sales_channel,sales_order_number,order_date_key,sales_amount,product_key,sales_territory_key);
        CREATE TABLE dim_date(date_key,calendar_date,calendar_year,calendar_quarter_name);
        CREATE TABLE dim_customer(customer_key,state_province_name,country_region_name,date_first_purchase,yearly_income,occupation);
        CREATE TABLE dim_product(product_key,category_name,subcategory_name);
        CREATE TABLE dim_sales_territory(sales_territory_key,territory_group,territory_country);
        INSERT INTO dim_date VALUES (1,'2026-01-01',2026,'Q1'),(2,'2026-07-01',2026,'Q3');
        INSERT INTO dim_customer VALUES (1,'Same State','US','2026-01-01',100000,'Professional'),(2,'Same State','US','2026-01-01',20000,'Manual'),(3,'Same State','US','2026-01-01',20000,'Manual'),(4,'Same State','CA','2026-01-01',NULL,NULL);
        INSERT INTO dim_product VALUES (1,'Bikes','Road Bikes'),(2,'Clothing','Jerseys');
        INSERT INTO dim_sales_territory VALUES (1,'North America','US'),(2,'North America','US'),(3,'North America','CA');
        INSERT INTO fct_sales VALUES (1,'Internet','A',1,10,1,1),(1,'Internet','A',1,15,1,1),(1,'Internet','B',1,20,1,1),(1,'Internet','C',2,30,2,1),(2,'Internet','D',1,40,1,1),(3,'Internet','E',1,50,1,1);
        """)
        sql = re.sub(r"`p.d.(\w+)`", r"\1", customer_ledger_sql("p", "d"))
        sql = (
            sql.replace("LEAST(", "MIN(")
            .replace(", QUARTER)", ", 'QUARTER')")
            .replace(", YEAR)", ", 'YEAR')")
            .replace(", DAY)", ", 'DAY')")
        )
        params = dict(
            year=None, quarter=None, channel=None, category=None, subcategory=None
        )
        rows = [dict(r) for r in db.execute(sql, params)]
        us = next(r for r in rows if r["country"] == "US")
        self.assertEqual(
            len(rows), 2
        )  # same name in different countries remains separate
        self.assertEqual(us["customers"], 3)
        self.assertEqual(us["revenue"], 165)
        self.assertEqual(us["dominant_income"], "Low Income (<30k)")
        self.assertEqual(
            us["top_occupation"], "Manual"
        )  # profiles, not transaction frequency
        self.assertEqual(us["dormant"], 2)
        bike = next(
            dict(r)
            for r in db.execute(sql, params | dict(category="Bikes"))
            if r["country"] == "US"
        )
        self.assertEqual(bike["revenue"], 135)
        self.assertEqual(bike["dormant"], 2)  # recent Clothing order prevents dormancy
        self.assertEqual(list(db.execute(sql, params | dict(channel="Reseller"))), [])

    def test_callback_and_export_contract(self):
        row = dict(
            state="California",
            country="US",
            territory="North America",
            customers=2,
            revenue=1234,
            average_orders=1.5,
            dormant=1,
            dominant_income="Low Income (<30k)",
            top_occupation="Manual",
            as_of="2026-07-01",
        )
        with (
            patch("pages.customers.load_filter_catalog", return_value=CATALOG),
            patch("pages.customers.load_customer_ledger", return_value=[row]) as loader,
        ):
            records, note = populate_customer_ledger(CATALOG, *([ALL] * 5))
            self.assertEqual(loader.call_args.args[2:], (None,) * 5)
            self.assertEqual(records[0]["state"], "California / US")
            self.assertEqual(records[0]["average_orders"], 1.5)
            self.assertIn("2026-07-01", note)
            with self.assertRaises(PreventUpdate):
                populate_customer_ledger(
                    CATALOG, ALL, ALL, ALL, "Clothing", "Road Bikes"
                )
            loader.side_effect = RuntimeError("private")
            self.assertIn(
                "Unable to load", populate_customer_ledger(CATALOG, *([ALL] * 5))[1]
            )
        table = customer_ledger_card().children[2].children
        self.assertEqual(len(table.columnDefs), 8)
        self.assertEqual(table.csvExportParams["exportedRows"], "filteredAndSorted")
        self.assertTrue(export_customer_ledger(1))
