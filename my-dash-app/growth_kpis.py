"""Growth scorecards from the monthly mart and order-grain daily history."""

from decimal import Decimal
import pandas as pd
from google.cloud import bigquery
from google.api_core.exceptions import NotFound
from revenue_kpis import cache, filter_parameters


def growth_scorecards_sql(project, dataset, product_filtered=False):
    # The mart has no product dimensions. Rebuild its monthly grain from filtered
    # facts for product selections rather than silently dropping those filters.
    monthly = (
        "SELECT DATE_TRUNC(order_date, MONTH) AS month, SUM(revenue) AS revenue FROM daily GROUP BY 1"
        if product_filtered
        else f"""SELECT DATE(calendar_year, month_number, 1) AS month,
                         SUM(periodic_gross_revenue) AS revenue
                  FROM `{project}.{dataset}.marts_growth_trends`
                  WHERE (@channel IS NULL OR sales_channel = @channel)
                  GROUP BY 1"""
    )
    return f"""
    WITH invoices AS (
      SELECT d.calendar_date AS order_date, s.sales_channel, s.sales_order_number,
             SUM(s.sales_amount) AS revenue
      FROM `{project}.{dataset}.fct_sales` s
      JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
      LEFT JOIN `{project}.{dataset}.dim_product` p ON s.product_key = p.product_key
      WHERE (@channel IS NULL OR s.sales_channel = @channel)
        AND (@category IS NULL OR COALESCE(p.category_name, 'Unknown') = @category)
        AND (@subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = @subcategory)
      GROUP BY 1, 2, 3
    ), daily AS (
      SELECT order_date, SUM(revenue) AS revenue,
             COUNTIF(sales_order_number IS NOT NULL) AS orders
      FROM invoices GROUP BY 1
    ), rolling AS (
      SELECT order_date,
             SUM(revenue) OVER (
               ORDER BY UNIX_DATE(order_date) RANGE BETWEEN 29 PRECEDING AND CURRENT ROW
             ) AS rolling_revenue
      FROM daily
    ), selected AS (
      SELECT * FROM daily
      WHERE (@year IS NULL OR EXTRACT(YEAR FROM order_date) = @year)
        AND (@quarter IS NULL OR CONCAT('Q', CAST(EXTRACT(QUARTER FROM order_date) AS STRING)) = @quarter)
    ), monthly AS ({monthly})
    SELECT
      ARRAY(SELECT AS STRUCT month, revenue FROM monthly ORDER BY month LIMIT 1201) AS monthly,
      (SELECT MAX(order_date) FROM selected) AS anchor_date,
      (SELECT MIN(order_date) FROM daily) AS first_date,
      (SELECT rolling_revenue FROM rolling WHERE order_date = (SELECT MAX(order_date) FROM selected)) AS rolling_revenue,
      (SELECT SAFE_DIVIDE(SUM(orders), COUNT(DISTINCT order_date)) FROM selected) AS order_velocity
    LIMIT 1
    """


@cache.memoize(timeout=60)
def load_growth_scorecards(
    project,
    dataset,
    year=None,
    quarter=None,
    channel=None,
    category=None,
    subcategory=None,
):
    with bigquery.Client(project=project) as client:
        use_facts = category is not None or subcategory is not None
        source = "Product-filtered sales facts" if use_facts else "Growth mart"
        if not use_facts:
            try:
                client.get_table(f"{project}.{dataset}.marts_growth_trends")
            except NotFound:
                use_facts = True
                source = "Sales facts (growth mart not deployed)"
        job = client.query(
            growth_scorecards_sql(project, dataset, use_facts),
            job_config=bigquery.QueryJobConfig(
                query_parameters=filter_parameters(
                    year, quarter, channel, category, subcategory
                ),
                maximum_bytes_billed=100 * 1024 * 1024,
                use_query_cache=True,
            ),
        )
        try:
            row = dict(next(iter(job.result(timeout=20))))
        except TimeoutError:
            job.cancel()
            raise
    if len(row["monthly"]) > 1200:
        raise ValueError("Growth history exceeds supported range")
    return {**row, "source": source}


def calculate_scorecards(data, year=None, quarter=None):
    monthly = {
        pd.Period(row["month"], freq="M"): Decimal(str(row["revenue"]))
        for row in data["monthly"]
    }
    selected = {
        m: value
        for m, value in monthly.items()
        if (year is None or m.year == year)
        and (quarter is None or f"Q{m.quarter}" == quarter)
    }
    empty = dict(
        qoq=None,
        yoy=None,
        rolling=None,
        peak=None,
        velocity=None,
        qoq_note="No matching sales",
        yoy_note="No matching sales",
        rolling_note="No matching sales",
        peak_note="No matching sales",
        velocity_note="No matching sales",
    )
    if not selected or data.get("anchor_date") is None:
        return empty
    latest = max(selected)
    current_q = latest.asfreq("Q")
    previous_q = current_q - 1
    quarterly = {}
    annual = {}
    for month, revenue in monthly.items():
        q = month.asfreq("Q")
        quarterly[q] = quarterly.get(q, Decimal(0)) + revenue
        if quarter is None or f"Q{month.quarter}" == quarter:
            annual[month.year] = annual.get(month.year, Decimal(0)) + revenue

    def change(current, previous):
        if current is None or previous is None or previous <= 0:
            return None
        return (current / previous - 1) * 100

    qoq = change(quarterly.get(current_q), quarterly.get(previous_q))
    yoy = change(annual.get(latest.year), annual.get(latest.year - 1))
    avg = sum(selected.values()) / len(selected)
    anchor = pd.Timestamp(data["anchor_date"])
    first = pd.Timestamp(data["first_date"])
    full_window = (anchor - first).days >= 29
    return dict(
        qoq=qoq,
        yoy=yoy,
        rolling=data.get("rolling_revenue") if full_window else None,
        peak=max(selected.values()) / avg if avg > 0 else None,
        velocity=data.get("order_velocity"),
        qoq_note=f"{current_q} vs {previous_q}"
        + (" · Baseline unavailable" if qoq is None else ""),
        yoy_note=f"{latest.year} vs {latest.year - 1}"
        + (f" · {quarter}" if quarter else "")
        + (" · Baseline unavailable" if yoy is None else ""),
        rolling_note=(
            f"Trailing 30-day revenue · through {anchor:%Y-%m-%d}"
            if full_window
            else "Fewer than 30 days of history"
        ),
        peak_note="Max / mean monthly revenue · months with sales",
        velocity_note="Distinct invoices / active sales dates",
    )


def day_type_sales_sql(project, dataset):
    return f"""
    SELECT d.calendar_year, d.month_number, d.is_weekend_flag,
           SUM(s.sales_amount) AS revenue
    FROM `{project}.{dataset}.fct_sales` s
    JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
    LEFT JOIN `{project}.{dataset}.dim_product` p ON s.product_key = p.product_key
    WHERE (@year IS NULL OR d.calendar_year = @year)
      AND (@quarter IS NULL OR d.calendar_quarter_name = @quarter)
      AND (@channel IS NULL OR s.sales_channel = @channel)
      AND (@category IS NULL OR COALESCE(p.category_name, 'Unknown') = @category)
      AND (@subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = @subcategory)
    GROUP BY 1, 2, 3
    ORDER BY 1, 2, 3
    LIMIT 2401
    """


@cache.memoize(timeout=60)
def load_day_type_sales(
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
            day_type_sales_sql(project, dataset),
            job_config=bigquery.QueryJobConfig(
                query_parameters=filter_parameters(
                    year, quarter, channel, category, subcategory
                ),
                maximum_bytes_billed=100 * 1024 * 1024,
                use_query_cache=True,
            ),
        )
        try:
            rows = [dict(row) for row in job.result(timeout=20)]
        except TimeoutError:
            job.cancel()
            raise
    if len(rows) > 2400:
        raise ValueError("Too many monthly segments")
    return rows


def seasonality_matrix_sql(project, dataset):
    return f"""
    SELECT d.month_number, TRIM(d.day_of_week_name) AS day_name,
           SUM(s.order_quantity) AS units
    FROM `{project}.{dataset}.fct_sales` s
    JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
    LEFT JOIN `{project}.{dataset}.dim_product` p ON s.product_key = p.product_key
    WHERE (@year IS NULL OR d.calendar_year = @year)
      AND (@quarter IS NULL OR d.calendar_quarter_name = @quarter)
      AND (@channel IS NULL OR s.sales_channel = @channel)
      AND (@category IS NULL OR COALESCE(p.category_name, 'Unknown') = @category)
      AND (@subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = @subcategory)
    GROUP BY 1, 2
    ORDER BY 1, 2
    LIMIT 84
    """


@cache.memoize(timeout=60)
def load_seasonality_matrix(
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
            seasonality_matrix_sql(project, dataset),
            job_config=bigquery.QueryJobConfig(
                query_parameters=filter_parameters(
                    year, quarter, channel, category, subcategory
                ),
                maximum_bytes_billed=100 * 1024 * 1024,
                use_query_cache=True,
            ),
        )
        try:
            return [dict(row) for row in job.result(timeout=20)]
        except TimeoutError:
            job.cancel()
            raise


def growth_ledger_sql(project, dataset):
    return f"""
    WITH invoices AS (
      SELECT DATE_TRUNC(d.calendar_date, MONTH) AS month,
             s.sales_channel, s.sales_order_number,
             SUM(s.sales_amount) AS revenue,
             SUM(CASE WHEN d.is_weekend_flag = FALSE THEN s.sales_amount ELSE 0 END) AS weekday_revenue,
             SUM(CASE WHEN d.is_weekend_flag = TRUE THEN s.sales_amount ELSE 0 END) AS weekend_revenue
      FROM `{project}.{dataset}.fct_sales` s
      JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
      LEFT JOIN `{project}.{dataset}.dim_product` p ON s.product_key = p.product_key
      WHERE (@channel IS NULL OR s.sales_channel = @channel)
        AND (@category IS NULL OR COALESCE(p.category_name, 'Unknown') = @category)
        AND (@subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = @subcategory)
      GROUP BY 1, 2, 3
    ), monthly AS (
      SELECT month, SUM(revenue) AS revenue,
             COUNTIF(sales_order_number IS NOT NULL) AS orders,
             SUM(weekday_revenue) AS weekday_revenue,
             SUM(weekend_revenue) AS weekend_revenue
      FROM invoices GROUP BY 1
    ), history AS (
      SELECT *, LAG(month) OVER (ORDER BY month) AS previous_month,
             LAG(revenue) OVER (ORDER BY month) AS previous_revenue
      FROM monthly
    )
    SELECT month, revenue, orders, weekday_revenue, weekend_revenue,
           SAFE_DIVIDE(weekend_revenue, revenue) * 100 AS weekend_share,
           CASE WHEN previous_month = DATE_SUB(month, INTERVAL 1 MONTH) AND previous_revenue > 0
                THEN (SAFE_DIVIDE(revenue, previous_revenue) - 1) * 100 END AS mom_growth
    FROM history
    WHERE (@year IS NULL OR EXTRACT(YEAR FROM month) = @year)
      AND (@quarter IS NULL OR CONCAT('Q', CAST(EXTRACT(QUARTER FROM month) AS STRING)) = @quarter)
    ORDER BY month
    LIMIT 1201
    """


@cache.memoize(timeout=60)
def load_growth_ledger(
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
            growth_ledger_sql(project, dataset),
            job_config=bigquery.QueryJobConfig(
                query_parameters=filter_parameters(
                    year, quarter, channel, category, subcategory
                ),
                maximum_bytes_billed=100 * 1024 * 1024,
                use_query_cache=True,
            ),
        )
        try:
            rows = [dict(row) for row in job.result(timeout=20)]
        except TimeoutError:
            job.cancel()
            raise
    if len(rows) > 1200:
        raise ValueError("Too many ledger months")
    return rows
