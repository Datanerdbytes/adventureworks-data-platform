"""Read-only, cached warehouse totals for the executive KPI strip."""

from datetime import datetime, timezone
from decimal import Decimal
import os
import re
import tempfile

import dash_bootstrap_components as dbc
from flask_caching import Cache
from google.cloud import bigquery
from components import metric

cache = Cache()
KPI_FIELDS = (
    ("gross_revenue_amount", "Gross revenue", "currency"),
    ("gross_profit_amount", "Gross profit", "currency"),
    ("gross_profit_margin_percentage", "Gross profit margin", "percent"),
    ("total_orders_count", "Total orders", "count"),
    ("average_order_value_aov", "Average order value", "currency"),
)


def init_kpi_cache(server):
    cache.init_app(
        server,
        config={
            "CACHE_TYPE": "FileSystemCache",
            "CACHE_DIR": tempfile.mkdtemp(prefix="adventureworks-kpis-"),
            "CACHE_DEFAULT_TIMEOUT": 60,
            "CACHE_THRESHOLD": 10,
        },
    )


def warehouse_location():
    project = os.environ.get("GBQ_PROJECT_ID", "quantum-echo-data-eng-prod")
    dataset = os.environ.get("BQ_ANALYTICS_DATASET", "gold_adventureworks")
    if not re.fullmatch(r"[a-z][a-z0-9-]*", project) or not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*", dataset
    ):
        raise ValueError("Invalid analytics project or dataset configuration")
    return project, dataset


def kpi_sql(project, dataset):
    # Product-level order counts overlap. Distinct channel/order pairs preserve
    # basket-level order identity without conflating the two sales channels.
    return f"""
    WITH financials AS (
      SELECT SUM(gross_revenue_amount) AS gross_revenue_amount,
             SUM(gross_profit_amount) AS gross_profit_amount,
             COUNT(*) AS source_rows,
             MIN(calendar_year) AS first_year, MAX(calendar_year) AS last_year
      FROM `{project}.{dataset}.revenue_sales_performance`
    ), orders AS (
      SELECT COUNT(*) AS total_orders_count FROM (
        SELECT DISTINCT s.sales_channel, s.sales_order_number
        FROM `{project}.{dataset}.fct_sales` AS s
        INNER JOIN `{project}.{dataset}.dim_date` AS d
          ON s.order_date_key = d.date_key
        WHERE s.sales_order_number IS NOT NULL
      )
    )
    SELECT gross_revenue_amount, gross_profit_amount,
           ROUND(SAFE_DIVIDE(gross_profit_amount, gross_revenue_amount) * 100, 2)
             AS gross_profit_margin_percentage,
           total_orders_count,
           ROUND(SAFE_DIVIDE(gross_revenue_amount, total_orders_count), 2)
             AS average_order_value_aov,
           source_rows, first_year, last_year
    FROM financials CROSS JOIN orders
    LIMIT 1
    """


@cache.memoize(timeout=60)
def load_revenue_kpis(project, dataset):
    with bigquery.Client(project=project) as client:
        job = client.query(
            kpi_sql(project, dataset),
            job_config=bigquery.QueryJobConfig(
                maximum_bytes_billed=100 * 1024 * 1024,
                use_query_cache=True,
            ),
        )
        try:
            row = next(iter(job.result(timeout=20)), None)
        except TimeoutError:
            job.cancel()
            raise
    if row is None or not row["source_rows"]:
        return None
    return {**dict(row), "fetched_at": datetime.now(timezone.utc).strftime("%H:%M UTC")}


def yoy_badge(key, kind, values):
    values = values or {}
    comparison = values.get("yoy", {})
    previous = comparison.get("previous") or {}
    current_value, prior_value = values.get(key), previous.get(key)
    label = comparison.get("reason", "YoY unavailable")
    tone = "neutral"
    title = label
    if comparison.get("period"):
        title = comparison["period"]
    if (
        current_value is not None
        and prior_value is not None
        and not comparison.get("reason")
    ):
        current, prior = Decimal(str(current_value)), Decimal(str(prior_value))
        if kind == "percent":
            change = current - prior
            unit = "pp"
        elif prior == 0:
            change = None
            unit = "%"
            label = "YoY N/A"
            title += " · Prior-year value is zero"
        else:
            change = (current - prior) / abs(prior) * 100
            unit = "%"
        if change is not None:
            rounded = change.quantize(Decimal("0.1"))
            direction = "↑" if rounded > 0 else "↓" if rounded < 0 else "→"
            tone = (
                "positive" if rounded > 0 else "negative" if rounded < 0 else "neutral"
            )
            label = f"{direction} {abs(rounded):.1f}{unit} YoY"
            title += f" · Previous: {prior:,.2f}; current: {current:,.2f}"
            if kind != "percent" and prior < 0:
                title += " · Change divided by absolute prior-year value"
    return dbc.Badge(
        label,
        color=None,
        className=f"kpi-yoy kpi-yoy--{tone}",
        title=title,
    )


def add_yoy_comparison(
    values, project, dataset, year, quarter, channel, category, subcategory
):
    comparison = {"reason": "Select year for YoY"}
    if year is not None:
        period = f"{year} {quarter or 'full year'} vs {year - 1} {quarter or 'full year'} · Same channel and product filters; available calendar-period totals"
        try:
            previous = load_executive_report(
                project, dataset, year - 1, quarter, channel, category, subcategory
            )
            comparison = {"period": period, "previous": previous}
            if not previous.get("source_rows"):
                comparison["reason"] = "No prior-year data"
            elif not values.get("source_rows"):
                comparison["reason"] = "No current-period data"
        except Exception:
            comparison = {"period": period, "reason": "YoY unavailable"}
    return {**values, "yoy": comparison}


def kpi_cards(values=None, note="All-time warehouse total"):
    cards = []
    for key, label, kind in KPI_FIELDS:
        value = (values or {}).get(key)
        if value is None:
            display = "—"
        elif kind == "currency":
            display = f"${Decimal(str(value)):,.2f}"
        elif kind == "percent":
            # The warehouse field is already a percentage, not a fraction.
            display = f"{Decimal(str(value)):,.2f}%"
        else:
            display = f"{int(value):,}"
        exact = display
        if value is not None and kind != "percent":
            number = Decimal(str(value))
            for threshold, suffix in (
                (10**12, "T"),
                (10**9, "B"),
                (10**6, "M"),
                (10**3, "K"),
            ):
                if abs(number) >= threshold:
                    compact = f"{number / threshold:.2f}".rstrip("0").rstrip(".")
                    display = f"{'$' if kind == 'currency' else ''}{compact}{suffix}"
                    break
        card = metric(label, display, note)
        if not note:
            card.children.pop(2)
        card.children[1].title = exact
        card.id = f"executive-kpi-{key}"
        card.children.append(yoy_badge(key, kind, values))
        cards.append(card)
    return cards


@cache.memoize(timeout=300)
def load_filter_catalog(project, dataset):
    sql = f"""SELECT DISTINCT calendar_year, calendar_quarter_name, sales_channel,
        product_category, product_subcategory
        FROM `{project}.{dataset}.revenue_sales_performance`
        ORDER BY calendar_year, calendar_quarter_name, sales_channel, product_category, product_subcategory
        LIMIT 10000"""
    with bigquery.Client(project=project) as client:
        rows = [
            dict(row)
            for row in client.query(
                sql,
                job_config=bigquery.QueryJobConfig(
                    maximum_bytes_billed=100 * 1024 * 1024
                ),
            ).result(timeout=20)
        ]
    return rows


def executive_sql(project, dataset):
    return f"""
    WITH filtered AS (
      SELECT calendar_year, calendar_quarter_name, month_name, sales_channel,
             product_category, product_subcategory, gross_revenue_amount,
             gross_profit_amount, total_units_sold
      FROM `{project}.{dataset}.revenue_sales_performance`
      WHERE (@year IS NULL OR calendar_year = @year)
        AND (@quarter IS NULL OR calendar_quarter_name = @quarter)
        AND (@channel IS NULL OR sales_channel = @channel)
        AND (@category IS NULL OR product_category = @category)
        AND (@subcategory IS NULL OR product_subcategory = @subcategory)
    ), financials AS (
      SELECT COALESCE(SUM(gross_revenue_amount), 0) AS gross_revenue_amount,
             COALESCE(SUM(gross_profit_amount), 0) AS gross_profit_amount,
             COUNT(*) AS source_rows FROM filtered
    ), orders AS (
      SELECT COUNT(*) AS total_orders_count FROM (
        SELECT DISTINCT s.sales_channel, s.sales_order_number
        FROM `{project}.{dataset}.fct_sales` s
        JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
        LEFT JOIN `{project}.{dataset}.dim_product` p ON s.product_key = p.product_key
        WHERE s.sales_order_number IS NOT NULL
          AND (@year IS NULL OR d.calendar_year = @year)
          AND (@quarter IS NULL OR d.calendar_quarter_name = @quarter)
          AND (@channel IS NULL OR s.sales_channel = @channel)
          AND (@category IS NULL OR COALESCE(p.category_name, 'Unknown') = @category)
          AND (@subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = @subcategory)
      )
    )
    SELECT financials.*, orders.total_orders_count,
      ROUND(SAFE_DIVIDE(gross_profit_amount, gross_revenue_amount)*100, 2) AS gross_profit_margin_percentage,
      ROUND(SAFE_DIVIDE(gross_revenue_amount, total_orders_count), 2) AS average_order_value_aov,
      ARRAY(SELECT AS STRUCT calendar_year, month_name, sales_channel,
          SUM(gross_revenue_amount) AS revenue, SUM(gross_profit_amount) AS profit
          FROM filtered GROUP BY calendar_year, month_name, sales_channel) AS monthly,
      ARRAY(SELECT AS STRUCT product_category, product_subcategory,
          SUM(gross_revenue_amount) AS revenue, SUM(gross_profit_amount) AS profit,
          SUM(total_units_sold) AS units
          FROM filtered GROUP BY product_category, product_subcategory
          ORDER BY revenue DESC) AS detail
    FROM financials CROSS JOIN orders LIMIT 1
    """


def filter_parameters(
    year=None, quarter=None, channel=None, category=None, subcategory=None
):
    return [
        bigquery.ScalarQueryParameter(name, kind, value)
        for name, kind, value in (
            ("year", "INT64", year),
            ("quarter", "STRING", quarter),
            ("channel", "STRING", channel),
            ("category", "STRING", category),
            ("subcategory", "STRING", subcategory),
        )
    ]


@cache.memoize(timeout=60)
def load_executive_report(
    project,
    dataset,
    year=None,
    quarter=None,
    channel=None,
    category=None,
    subcategory=None,
):
    with bigquery.Client(project=project) as client:
        job = client.query(
            executive_sql(project, dataset),
            job_config=bigquery.QueryJobConfig(
                query_parameters=filter_parameters(
                    year, quarter, channel, category, subcategory
                ),
                maximum_bytes_billed=100 * 1024 * 1024,
                use_query_cache=True,
            ),
        )
        try:
            row = next(iter(job.result(timeout=20)))
        except TimeoutError:
            job.cancel()
            raise
    return {**dict(row), "fetched_at": datetime.now(timezone.utc).strftime("%H:%M UTC")}
