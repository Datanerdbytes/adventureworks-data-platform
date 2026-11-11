import unittest
from unittest.mock import patch
from test_customer_kpis import CATALOG, ALL
from customer_kpis import customer_ledger_sql
from pages.customers import (
    populate_customer_ledger,
    customer_ledger_card,
    export_customer_ledger,
)
from warehouse_fixture import connect, rows as fetch_rows
from dash.exceptions import PreventUpdate


class CustomerLedgerTests(unittest.TestCase):
    def test_customer_weighted_modes_geography_and_order_grain(self):
        db = connect("""
        CREATE TABLE fct_sales(customer_key INTEGER,sales_channel VARCHAR,sales_order_number VARCHAR,order_date_key INTEGER,sales_amount DOUBLE,product_key INTEGER,sales_territory_key INTEGER);
        CREATE TABLE dim_date(date_key INTEGER,calendar_date DATE,calendar_year INTEGER,calendar_quarter_name VARCHAR);
        CREATE TABLE dim_customer(customer_key INTEGER,state_province_name VARCHAR,country_region_name VARCHAR,date_first_purchase DATE,yearly_income DOUBLE,occupation VARCHAR);
        CREATE TABLE dim_product(product_key INTEGER,category_name VARCHAR,subcategory_name VARCHAR);
        CREATE TABLE dim_sales_territory(sales_territory_key INTEGER,territory_group VARCHAR,territory_country VARCHAR);
        INSERT INTO dim_date VALUES (1,DATE '2026-01-01',2026,'Q1'),(2,DATE '2026-07-01',2026,'Q3');
        INSERT INTO dim_customer VALUES (1,'Same State','US',DATE '2026-01-01',100000,'Professional'),(2,'Same State','US',DATE '2026-01-01',20000,'Manual'),(3,'Same State','US',DATE '2026-01-01',20000,'Manual'),(4,'Same State','CA',DATE '2026-01-01',NULL,NULL);
        INSERT INTO dim_product VALUES (1,'Bikes','Road Bikes'),(2,'Clothing','Jerseys');
        INSERT INTO dim_sales_territory VALUES (1,'North America','US'),(2,'North America','US'),(3,'North America','CA');
        INSERT INTO fct_sales VALUES (1,'Internet','A',1,10,1,1),(1,'Internet','A',1,15,1,1),(1,'Internet','B',1,20,1,1),(1,'Internet','C',2,30,2,1),(2,'Internet','D',1,40,1,1),(3,'Internet','E',1,50,1,1);
        """)
        self.addCleanup(db.close)
        sql = customer_ledger_sql("p", "d")
        params = dict(
            year=None, quarter=None, channel=None, category=None, subcategory=None
        )
        rows = fetch_rows(db, sql, params)
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
            row
            for row in fetch_rows(db, sql, params | dict(category="Bikes"))
            if row["country"] == "US"
        )
        self.assertEqual(bike["revenue"], 135)
        self.assertEqual(bike["dormant"], 2)  # recent Clothing order prevents dormancy
        self.assertEqual(
            db.execute(sql, params | dict(channel="Reseller")).fetchall(), []
        )

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
