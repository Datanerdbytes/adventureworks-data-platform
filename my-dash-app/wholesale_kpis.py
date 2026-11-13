"""Filter-aware wholesale account and revenue metrics."""

from warehouse_cache import warehouse_memoize

from revenue_kpis import cache, filter_parameters
from revenue_kpis import (
    validate_warehouse_identifiers as validate_warehouse_identifiers,
)
from warehouse_client import query_rows


def active_accounts_sql(project, dataset):
    validate_warehouse_identifiers(project, dataset)
    return """
    SELECT COUNT(DISTINCT s.reseller_key) AS active_accounts
    FROM gold_adventureworks.fct_sales s
    JOIN gold_adventureworks.dim_date d ON s.order_date_key = d.date_key
    LEFT JOIN gold_adventureworks.dim_product p ON s.product_key = p.product_key
    WHERE s.sales_channel = 'Reseller'
      AND s.sales_order_number IS NOT NULL
      AND ($year IS NULL OR d.calendar_year = $year)
      AND ($quarter IS NULL OR d.calendar_quarter_name = $quarter)
      AND ($channel IS NULL OR s.sales_channel = $channel)
      AND ($category IS NULL OR COALESCE(p.category_name, 'Unknown') = $category)
      AND ($subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = $subcategory)
    LIMIT 1
    """  # nosec B608


@warehouse_memoize(cache)
def load_active_accounts(
    project,
    dataset,
    year=None,
    quarter=None,
    channel=None,
    category=None,
    subcategory=None,
):
    validate_warehouse_identifiers(project, dataset)
    parameters = filter_parameters(year, quarter, channel, category, subcategory)
    row = query_rows(active_accounts_sql(project, dataset), parameters)[0]
    return int(row["active_accounts"])


def reseller_revenue_sql(project, dataset):
    validate_warehouse_identifiers(project, dataset)
    return """
    SELECT COALESCE(SUM(gross_revenue_amount), 0) AS total_reseller_revenue,
           COALESCE(SUM(total_units_sold), 0) AS total_wholesale_units_sold,
           COUNT(*) AS source_rows
    FROM gold_adventureworks.revenue_sales_performance
    WHERE sales_channel = 'Reseller'
      AND ($year IS NULL OR calendar_year = $year)
      AND ($quarter IS NULL OR calendar_quarter_name = $quarter)
      AND ($channel IS NULL OR sales_channel = $channel)
      AND ($category IS NULL OR product_category = $category)
      AND ($subcategory IS NULL OR product_subcategory = $subcategory)
    LIMIT 1
    """  # nosec B608


@warehouse_memoize(cache)
def load_reseller_revenue(
    project,
    dataset,
    year=None,
    quarter=None,
    channel=None,
    category=None,
    subcategory=None,
):
    validate_warehouse_identifiers(project, dataset)
    parameters = filter_parameters(year, quarter, channel, category, subcategory)
    return query_rows(reseller_revenue_sql(project, dataset), parameters)[0]


def wholesale_orders_sql(project, dataset):
    validate_warehouse_identifiers(project, dataset)
    return """
    SELECT COUNT(DISTINCT s.sales_order_number) AS wholesale_orders
    FROM gold_adventureworks.fct_sales s
    JOIN gold_adventureworks.dim_date d ON s.order_date_key = d.date_key
    LEFT JOIN gold_adventureworks.dim_product p ON s.product_key = p.product_key
    WHERE s.sales_channel = 'Reseller'
      AND s.sales_order_number IS NOT NULL
      AND ($year IS NULL OR d.calendar_year = $year)
      AND ($quarter IS NULL OR d.calendar_quarter_name = $quarter)
      AND ($channel IS NULL OR s.sales_channel = $channel)
      AND ($category IS NULL OR COALESCE(p.category_name, 'Unknown') = $category)
      AND ($subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = $subcategory)
    LIMIT 1
    """  # nosec B608


@warehouse_memoize(cache)
def load_wholesale_orders(
    project,
    dataset,
    year=None,
    quarter=None,
    channel=None,
    category=None,
    subcategory=None,
):
    validate_warehouse_identifiers(project, dataset)
    parameters = filter_parameters(year, quarter, channel, category, subcategory)
    row = query_rows(wholesale_orders_sql(project, dataset), parameters)[0]
    return int(row["wholesale_orders"])


@warehouse_memoize(cache, coalesce=False)
def load_wholesale_comparison(
    project, dataset, year, quarter, channel, category, subcategory
):
    """One cached prior-period snapshot shared by all five YoY badges."""
    validate_warehouse_identifiers(project, dataset)
    from decimal import Decimal

    params = (project, dataset, year, quarter, channel, category, subcategory)
    totals = load_reseller_revenue(*params)
    accounts = load_active_accounts(*params)
    orders = load_wholesale_orders(*params)
    revenue = Decimal(str(totals["total_reseller_revenue"]))
    return {
        **totals,
        "active_accounts": accounts,
        "revenue_per_reseller": revenue / accounts if accounts else None,
        "wholesale_aov": revenue / orders if orders else None,
    }


def top_resellers_sql(project, dataset):
    validate_warehouse_identifiers(project, dataset)
    return """
    SELECT r.reseller_name, SUM(s.sales_amount) AS revenue
    FROM gold_adventureworks.fct_sales s
    JOIN gold_adventureworks.dim_reseller r ON s.reseller_key = r.reseller_key
    JOIN gold_adventureworks.dim_date d ON s.order_date_key = d.date_key
    LEFT JOIN gold_adventureworks.dim_product p ON s.product_key = p.product_key
    WHERE s.sales_channel = 'Reseller'
      AND ($year IS NULL OR d.calendar_year = $year)
      AND ($quarter IS NULL OR d.calendar_quarter_name = $quarter)
      AND ($channel IS NULL OR s.sales_channel = $channel)
      AND ($category IS NULL OR COALESCE(p.category_name, 'Unknown') = $category)
      AND ($subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = $subcategory)
    GROUP BY r.reseller_name
    ORDER BY revenue DESC, r.reseller_name ASC
    LIMIT 10
    """  # nosec B608


@warehouse_memoize(cache)
def load_top_resellers(
    project,
    dataset,
    year=None,
    quarter=None,
    channel=None,
    category=None,
    subcategory=None,
):
    validate_warehouse_identifiers(project, dataset)
    parameters = filter_parameters(year, quarter, channel, category, subcategory)
    return query_rows(top_resellers_sql(project, dataset), parameters)


def reseller_scatter_sql(project, dataset):
    validate_warehouse_identifiers(project, dataset)
    return """
    SELECT r.reseller_key, r.reseller_name, r.annual_revenue,
           SUM(s.order_quantity) AS total_units_sold
    FROM gold_adventureworks.fct_sales s
    JOIN gold_adventureworks.dim_reseller r ON s.reseller_key = r.reseller_key
    JOIN gold_adventureworks.dim_date d ON s.order_date_key = d.date_key
    LEFT JOIN gold_adventureworks.dim_product p ON s.product_key = p.product_key
    WHERE s.sales_channel = 'Reseller'
      AND r.annual_revenue IS NOT NULL
      AND ($year IS NULL OR d.calendar_year = $year)
      AND ($quarter IS NULL OR d.calendar_quarter_name = $quarter)
      AND ($channel IS NULL OR s.sales_channel = $channel)
      AND ($category IS NULL OR COALESCE(p.category_name, 'Unknown') = $category)
      AND ($subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = $subcategory)
    GROUP BY r.reseller_key, r.reseller_name, r.annual_revenue
    ORDER BY r.reseller_key
    LIMIT 1001
    """  # nosec B608


@warehouse_memoize(cache)
def load_reseller_scatter(
    project,
    dataset,
    year=None,
    quarter=None,
    channel=None,
    category=None,
    subcategory=None,
):
    validate_warehouse_identifiers(project, dataset)
    parameters = filter_parameters(year, quarter, channel, category, subcategory)
    return query_rows(reseller_scatter_sql(project, dataset), parameters)


def wholesale_product_mix_sql(project, dataset):
    validate_warehouse_identifiers(project, dataset)
    return """
    SELECT product_category, SUM(gross_revenue_amount) AS revenue
    FROM gold_adventureworks.revenue_sales_performance
    WHERE sales_channel = 'Reseller'
      AND ($year IS NULL OR calendar_year = $year)
      AND ($quarter IS NULL OR calendar_quarter_name = $quarter)
      AND ($channel IS NULL OR sales_channel = $channel)
      AND ($category IS NULL OR product_category = $category)
      AND ($subcategory IS NULL OR product_subcategory = $subcategory)
    GROUP BY product_category
    ORDER BY product_category
    LIMIT 1001
    """  # nosec B608


@warehouse_memoize(cache)
def load_wholesale_product_mix(
    project,
    dataset,
    year=None,
    quarter=None,
    channel=None,
    category=None,
    subcategory=None,
):
    validate_warehouse_identifiers(project, dataset)
    parameters = filter_parameters(year, quarter, channel, category, subcategory)
    return query_rows(wholesale_product_mix_sql(project, dataset), parameters)


def wholesale_operations_sql(project, dataset, staging_dataset):
    validate_warehouse_identifiers(project, dataset)
    validate_warehouse_identifiers(project, staging_dataset)
    # The silver staging fact is the shipped artifact's silver schema; the
    # configured staging dataset stays validated for filter consistency.
    return """
    WITH invoices AS (
      SELECT s.reseller_key, s.sales_order_number,
             SUM(s.order_quantity) AS units,
             AVG(DATE_DIFF('day', s.order_date, s.ship_date)) AS lead_days
      FROM silver_adventureworks.stg_fact_reseller_sales s
      JOIN gold_adventureworks.dim_date d ON s.order_date_key = d.date_key
      LEFT JOIN gold_adventureworks.dim_product p ON s.product_key = p.product_key
      WHERE s.sales_order_number IS NOT NULL
        AND ($year IS NULL OR d.calendar_year = $year)
        AND ($quarter IS NULL OR d.calendar_quarter_name = $quarter)
        AND ($channel IS NULL OR $channel = 'Reseller')
        AND ($category IS NULL OR COALESCE(p.category_name, 'Unknown') = $category)
        AND ($subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = $subcategory)
      GROUP BY s.reseller_key, s.sales_order_number
    )
    SELECT r.reseller_key, TRIM(r.reseller_name) AS reseller_name,
           r.order_frequency,
           COUNT(*) AS total_orders_count,
           SUM(i.units) / COUNT(*) AS average_units_per_order,
           AVG(i.lead_days) AS average_shipping_lead_days,
           r.state_province_name, r.country_region_name
    FROM invoices i
    JOIN gold_adventureworks.dim_reseller r ON i.reseller_key = r.reseller_key
    GROUP BY r.reseller_key, r.reseller_name, r.order_frequency,
             r.state_province_name, r.country_region_name
    ORDER BY average_shipping_lead_days DESC, r.reseller_name, r.reseller_key
    LIMIT 1001
    """  # nosec B608


@warehouse_memoize(cache)
def load_wholesale_operations(
    project,
    dataset,
    staging_dataset,
    year=None,
    quarter=None,
    channel=None,
    category=None,
    subcategory=None,
):
    validate_warehouse_identifiers(project, dataset)
    validate_warehouse_identifiers(project, staging_dataset)
    parameters = filter_parameters(year, quarter, channel, category, subcategory)
    return query_rows(
        wholesale_operations_sql(project, dataset, staging_dataset), parameters
    )
