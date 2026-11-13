"""Read-only, cached warehouse totals for the executive KPI strip."""

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import re
import tempfile
from typing import NamedTuple

import dash_bootstrap_components as dbc
from flask_caching import Cache
from components import metric, sparkline
from theme import TOKENS
from warehouse_cache import positive_threshold, positive_lock_timeout, warehouse_memoize
from warehouse_client import query_rows

cache = Cache()
KPI_FIELDS = (
    ("gross_revenue_amount", "Gross revenue", "currency"),
    ("gross_profit_amount", "Gross profit", "currency"),
    ("gross_profit_margin_percentage", "Gross profit margin", "percent"),
    ("total_orders_count", "Total orders", "count"),
    ("average_order_value_aov", "Average order value", "currency"),
)

REVENUE_HOVERTEMPLATE = "%{x|%b %Y}<br>Gross revenue: $%{y:,.2f}<extra></extra>"
MARGIN_HOVERTEMPLATE = "%{x|%b %Y}<br>Gross profit margin: %{y:.2f}%<extra></extra>"
PROFIT_HOVERTEMPLATE = "%{x|%b %Y}<br>Gross profit: $%{y:,.2f}<extra></extra>"
ORDERS_HOVERTEMPLATE = "%{x|%b %Y}<br>Orders: %{y:,.0f}<extra></extra>"
AOV_HOVERTEMPLATE = "%{x|%b %Y}<br>Avg order value: $%{y:,.2f}<extra></extra>"


def init_kpi_cache(server):
    threshold = positive_threshold(
        server.config.get(
            "KPI_CACHE_THRESHOLD", os.environ.get("KPI_CACHE_THRESHOLD", "500")
        )
    )
    lock_timeout = positive_lock_timeout(
        server.config.get(
            "KPI_CACHE_LOCK_TIMEOUT_SECONDS",
            os.environ.get("KPI_CACHE_LOCK_TIMEOUT_SECONDS", "30"),
        )
    )
    server.config["KPI_CACHE_THRESHOLD"] = threshold
    server.config["KPI_CACHE_LOCK_TIMEOUT_SECONDS"] = lock_timeout
    # Gunicorn workers must share the cache and locks to coalesce cold loads.
    namespace = hashlib.sha256(
        str(Path(__file__).resolve().parent).encode()
    ).hexdigest()[:16]
    cache_dir = Path(tempfile.gettempdir()) / f"adventureworks-kpis-{namespace}"
    cache_dir.mkdir(mode=0o700, exist_ok=True)
    lock_dir = Path(tempfile.gettempdir()) / f"adventureworks-query-locks-{namespace}"
    lock_dir.mkdir(mode=0o700, exist_ok=True)
    server.extensions["executive_query_lock_dir"] = lock_dir
    cache.init_app(
        server,
        config={
            "CACHE_TYPE": "FileSystemCache",
            "CACHE_DIR": str(cache_dir),
            "CACHE_DEFAULT_TIMEOUT": 60,
            "CACHE_THRESHOLD": threshold,
        },
    )


def validate_warehouse_identifiers(project, dataset):
    """Allow only identifier characters; SQL values must still be bound separately."""
    if (
        not isinstance(project, str)
        or not isinstance(dataset, str)
        or not re.fullmatch(r"[a-z][a-z0-9-]*", project)
        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", dataset)
    ):
        raise ValueError("Invalid analytics project or dataset configuration")


def warehouse_location():
    project = os.environ.get("GBQ_PROJECT_ID", "quantum-echo-data-eng-prod")
    dataset = os.environ.get("BQ_ANALYTICS_DATASET", "gold_adventureworks")
    validate_warehouse_identifiers(project, dataset)
    return project, dataset


def kpi_sql(project, dataset):
    # Product-level order counts overlap. Distinct channel/order pairs preserve
    # basket-level order identity without conflating the two sales channels.
    #
    # The mart/fact tables live in the shipped artifact's gold schema; whether
    # the configured dataset matches is still validated for filter consistency.
    validate_warehouse_identifiers(project, dataset)
    return """
    WITH financials AS (
      SELECT SUM(gross_revenue_amount) AS gross_revenue_amount,
             SUM(gross_profit_amount) AS gross_profit_amount,
             COUNT(*) AS source_rows,
             MIN(calendar_year) AS first_year, MAX(calendar_year) AS last_year
      FROM gold_adventureworks.revenue_sales_performance
    ), orders AS (
      SELECT COUNT(*) AS total_orders_count FROM (
        SELECT DISTINCT s.sales_channel, s.sales_order_number
        FROM gold_adventureworks.fct_sales AS s
        INNER JOIN gold_adventureworks.dim_date AS d
          ON s.order_date_key = d.date_key
        WHERE s.sales_order_number IS NOT NULL
      )
    )
    SELECT gross_revenue_amount, gross_profit_amount,
           ROUND(CASE WHEN gross_revenue_amount = 0 THEN NULL
                      ELSE gross_profit_amount / gross_revenue_amount END * 100, 2)
             AS gross_profit_margin_percentage,
           total_orders_count,
           ROUND(CASE WHEN total_orders_count = 0 THEN NULL
                      ELSE gross_revenue_amount / total_orders_count END, 2)
             AS average_order_value_aov,
           source_rows, first_year, last_year
    FROM financials CROSS JOIN orders
    LIMIT 1
    """  # nosec B608


@warehouse_memoize(cache)
def load_revenue_kpis(project, dataset):
    validate_warehouse_identifiers(project, dataset)
    row = next(iter(query_rows(kpi_sql(project, dataset))), None)
    if row is None or not row["source_rows"]:
        return None
    return {**row, "fetched_at": datetime.now(timezone.utc).strftime("%H:%M UTC")}


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


MONTH_INDEX = {
    month: number
    for number, month in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        start=1,
    )
}


class MonthlyPoint(NamedTuple):
    """One summed calendar month, so consumers never unpack positions."""

    year: int
    month: int
    revenue: Decimal
    profit: Decimal


def monthly_points(monthly) -> list[MonthlyPoint]:
    """Aggregate monthly mart rows into sorted calendar-month sums.

    Channels overlap within a month, so measures are summed before trending;
    rows with unknown month names or years are ignored rather than guessed.
    """
    totals: dict[tuple[int, int], tuple[Decimal, Decimal]] = {}
    for row in monthly or []:
        month = MONTH_INDEX.get(str(row.get("month_name") or "").strip().title())
        year = row.get("calendar_year")
        if month is None or year is None:
            continue
        bucket = (int(year), month)
        current = totals.get(bucket, (Decimal("0"), Decimal("0")))
        totals[bucket] = (
            current[0] + Decimal(str(row.get("revenue") or 0)),
            current[1] + Decimal(str(row.get("profit") or 0)),
        )
    return [
        MonthlyPoint(year, month, *totals[(year, month)])
        for year, month in sorted(totals)
    ]


class MonthlyOrderPoint(NamedTuple):
    """One calendar month's distinct order count, aligned with MonthlyPoint."""

    year: int
    month: int
    orders: int


def monthly_order_points(monthly_orders) -> list[MonthlyOrderPoint]:
    """Aggregate monthly order rows into sorted calendar-month sums.

    Buckets are disjoint because an order has a single order date, so summing
    per-month distinct channel/order counts reproduces the all-time total.
    Rows with unknown years or months are ignored rather than guessed.
    """
    totals: dict[tuple[int, int], int] = {}
    for row in monthly_orders or []:
        year = row.get("calendar_year")
        month = row.get("month_number")
        if year is None or month is None:
            continue
        bucket = (int(year), int(month))
        totals[bucket] = totals.get(bucket, 0) + int(row.get("orders") or 0)
    return [
        MonthlyOrderPoint(year, month, totals[(year, month)])
        for year, month in sorted(totals)
    ]


def margin_percentage(revenue, profit):
    """Margin from sums; zero revenue leaves a gap instead of a fake zero."""
    return profit / revenue * 100 if revenue != 0 else None


def kpi_sparkline(key, monthly, monthly_orders=None):
    """Tiny trend line for one KPI from the already-loaded monthly rows.

    Revenue, profit, and margin trend the monthly revenue mart sums. Orders
    and AOV trend the distinct channel/order pairs from fct_sales — the same
    order identity the headline totals use, so no overlapping product-level
    count is invented. Zero revenue or order periods leave gaps instead of
    fake zeros.
    """
    points = monthly_points(monthly)
    if len(points) < 2:
        return None
    x = [datetime(point.year, point.month, 1) for point in points]
    if key == "gross_profit_margin_percentage":
        ys = [
            margin_percentage(float(point.revenue), float(point.profit))
            for point in points
        ]
        color = TOKENS["teal"]
        hovertemplate = MARGIN_HOVERTEMPLATE
    elif key == "gross_revenue_amount":
        ys = [float(point.revenue) for point in points]
        color = TOKENS["primary"]
        hovertemplate = REVENUE_HOVERTEMPLATE
    elif key == "gross_profit_amount":
        ys = [float(point.profit) for point in points]
        color = TOKENS["primary"]
        hovertemplate = PROFIT_HOVERTEMPLATE
    elif key == "total_orders_count":
        order_points = monthly_order_points(monthly_orders)
        if len(order_points) < 2:
            return None
        return sparkline(
            [datetime(point.year, point.month, 1) for point in order_points],
            [float(point.orders) for point in order_points],
            TOKENS["primary"],
            ORDERS_HOVERTEMPLATE,
        )
    elif key == "average_order_value_aov":
        order_points = monthly_order_points(monthly_orders)
        if len(order_points) < 2:
            return None
        orders = {point[:2]: point.orders for point in order_points}
        ys = [
            (
                float(point.revenue) / orders[(point.year, point.month)]
                if orders.get((point.year, point.month))
                else None
            )
            for point in points
        ]
        color = TOKENS["primary"]
        hovertemplate = AOV_HOVERTEMPLATE
    else:
        return None
    return sparkline(x, ys, color, hovertemplate)


def kpi_cards(
    values=None, note="All-time warehouse total", monthly=None, monthly_orders=None
):
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
        card = metric(
            label,
            display,
            note,
            sparkline=kpi_sparkline(key, monthly, monthly_orders) if values else None,
        )
        if not note:
            card.children.pop(2)
        card.children[1].title = exact
        card.id = f"executive-kpi-{key}"
        card.children.append(yoy_badge(key, kind, values))
        cards.append(card)
    return cards


@warehouse_memoize(cache)
def load_filter_catalog(project, dataset):
    validate_warehouse_identifiers(project, dataset)
    sql = """SELECT DISTINCT calendar_year, calendar_quarter_name, sales_channel,
        product_category, product_subcategory
        FROM gold_adventureworks.revenue_sales_performance
        ORDER BY calendar_year, calendar_quarter_name, sales_channel, product_category, product_subcategory
        LIMIT 10000"""
    return query_rows(sql)


def executive_financials_sql(project, dataset):
    validate_warehouse_identifiers(project, dataset)
    return """
    WITH filtered AS (
      SELECT calendar_year, calendar_quarter_name, month_name, sales_channel,
             product_category, product_subcategory, gross_revenue_amount,
             gross_profit_amount, total_units_sold
      FROM gold_adventureworks.revenue_sales_performance
      WHERE ($year IS NULL OR calendar_year = $year)
        AND ($quarter IS NULL OR calendar_quarter_name = $quarter)
        AND ($channel IS NULL OR sales_channel = $channel)
        AND ($category IS NULL OR product_category = $category)
        AND ($subcategory IS NULL OR product_subcategory = $subcategory)
    )
    SELECT COALESCE(SUM(gross_revenue_amount), 0) AS gross_revenue_amount,
           COALESCE(SUM(gross_profit_amount), 0) AS gross_profit_amount,
           COUNT(*) AS source_rows,
           CASE WHEN SUM(gross_revenue_amount) = 0 THEN NULL
                ELSE SUM(gross_profit_amount) / SUM(gross_revenue_amount) END
             * 100 AS gross_profit_margin_percentage
    FROM filtered
    """


def executive_monthly_sql(project, dataset):
    validate_warehouse_identifiers(project, dataset)
    return """
    SELECT calendar_year, month_name, sales_channel,
           SUM(gross_revenue_amount) AS revenue,
           SUM(gross_profit_amount) AS profit
    FROM gold_adventureworks.revenue_sales_performance
    WHERE ($year IS NULL OR calendar_year = $year)
      AND ($quarter IS NULL OR calendar_quarter_name = $quarter)
      AND ($channel IS NULL OR sales_channel = $channel)
      AND ($category IS NULL OR product_category = $category)
      AND ($subcategory IS NULL OR product_subcategory = $subcategory)
    GROUP BY calendar_year, month_name, sales_channel
    ORDER BY calendar_year, month_name, sales_channel
    """


def executive_detail_sql(project, dataset):
    validate_warehouse_identifiers(project, dataset)
    return """
    SELECT product_category, product_subcategory,
           SUM(gross_revenue_amount) AS revenue,
           SUM(gross_profit_amount) AS profit,
           SUM(total_units_sold) AS units
    FROM gold_adventureworks.revenue_sales_performance
    WHERE ($year IS NULL OR calendar_year = $year)
      AND ($quarter IS NULL OR calendar_quarter_name = $quarter)
      AND ($channel IS NULL OR sales_channel = $channel)
      AND ($category IS NULL OR product_category = $category)
      AND ($subcategory IS NULL OR product_subcategory = $subcategory)
    GROUP BY product_category, product_subcategory
    ORDER BY revenue DESC, product_category, product_subcategory
    """


def executive_orders_sql(project, dataset):
    validate_warehouse_identifiers(project, dataset)
    return """
    SELECT COUNT(*) AS total_orders_count FROM (
      SELECT DISTINCT s.sales_channel, s.sales_order_number
      FROM gold_adventureworks.fct_sales s
      JOIN gold_adventureworks.dim_date d ON s.order_date_key = d.date_key
      LEFT JOIN gold_adventureworks.dim_product p ON s.product_key = p.product_key
      WHERE s.sales_order_number IS NOT NULL
        AND ($year IS NULL OR d.calendar_year = $year)
        AND ($quarter IS NULL OR d.calendar_quarter_name = $quarter)
        AND ($channel IS NULL OR s.sales_channel = $channel)
        AND ($category IS NULL OR COALESCE(p.category_name, 'Unknown') = $category)
        AND ($subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = $subcategory)
    )
    """


def executive_monthly_orders_sql(project, dataset):
    """Monthly distinct channel/order pairs under the same filters as the total.

    Grouping includes the channel so COUNT(DISTINCT sales_order_number) within
    each group equals distinct channel/order pairs; the buckets stay disjoint
    across months because an order has one order date.
    """
    validate_warehouse_identifiers(project, dataset)
    return """
    SELECT d.calendar_year AS calendar_year, d.month_number AS month_number,
           s.sales_channel AS sales_channel,
           COUNT(DISTINCT s.sales_order_number) AS orders
    FROM gold_adventureworks.fct_sales s
    JOIN gold_adventureworks.dim_date d ON s.order_date_key = d.date_key
    LEFT JOIN gold_adventureworks.dim_product p ON s.product_key = p.product_key
    WHERE s.sales_order_number IS NOT NULL
      AND ($year IS NULL OR d.calendar_year = $year)
      AND ($quarter IS NULL OR d.calendar_quarter_name = $quarter)
      AND ($channel IS NULL OR s.sales_channel = $channel)
      AND ($category IS NULL OR COALESCE(p.category_name, 'Unknown') = $category)
      AND ($subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = $subcategory)
    GROUP BY d.calendar_year, d.month_number, s.sales_channel
    ORDER BY d.calendar_year, d.month_number, s.sales_channel
    """  # nosec B608


def filter_parameters(
    year=None, quarter=None, channel=None, category=None, subcategory=None
):
    """Named-parameter binding shared by every loader's five sales filters."""
    return {
        "year": year,
        "quarter": quarter,
        "channel": channel,
        "category": category,
        "subcategory": subcategory,
    }


def load_executive_report(
    project,
    dataset,
    year=None,
    quarter=None,
    channel=None,
    category=None,
    subcategory=None,
):
    validate_warehouse_identifiers(project, dataset)
    filters = (project, dataset, year, quarter, channel, category, subcategory)
    return _load_executive_report(*filters)


@warehouse_memoize(cache)
def _load_executive_report(
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
    financial = query_rows(executive_financials_sql(project, dataset), parameters)
    if not financial:
        raise RuntimeError("Executive financials query returned no rows")
    financials = financial[0]
    orders = query_rows(executive_orders_sql(project, dataset), parameters)
    total_orders = orders[0]["total_orders_count"] if orders else 0
    monthly = query_rows(executive_monthly_sql(project, dataset), parameters)
    monthly_orders = query_rows(
        executive_monthly_orders_sql(project, dataset), parameters
    )
    detail = query_rows(executive_detail_sql(project, dataset), parameters)
    margin = financials["gross_profit_margin_percentage"]
    revenue = Decimal(str(financials["gross_revenue_amount"] or 0))
    report = {
        **financials,
        "total_orders_count": total_orders,
        "gross_profit_margin_percentage": None if margin is None else round(margin, 2),
        "average_order_value_aov": (
            None if not total_orders else round(revenue / Decimal(str(total_orders)), 2)
        ),
        "monthly": monthly,
        "monthly_orders": monthly_orders,
        "detail": detail,
        "fetched_at": datetime.now(timezone.utc).strftime("%H:%M UTC"),
    }
    return report
