"""Filter-aware wholesale account and revenue metrics."""

from google.cloud import bigquery
from revenue_kpis import cache, filter_parameters


def active_accounts_sql(project, dataset):
    return f"""
    SELECT COUNT(DISTINCT s.reseller_key) AS active_accounts
    FROM `{project}.{dataset}.fct_sales` s
    JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
    LEFT JOIN `{project}.{dataset}.dim_product` p ON s.product_key = p.product_key
    WHERE s.sales_channel = 'Reseller'
      AND s.sales_order_number IS NOT NULL
      AND (@year IS NULL OR d.calendar_year = @year)
      AND (@quarter IS NULL OR d.calendar_quarter_name = @quarter)
      AND (@channel IS NULL OR s.sales_channel = @channel)
      AND (@category IS NULL OR COALESCE(p.category_name, 'Unknown') = @category)
      AND (@subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = @subcategory)
    LIMIT 1
    """


@cache.memoize(timeout=60)
def load_active_accounts(
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
            active_accounts_sql(project, dataset),
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
    return int(row["active_accounts"])


def reseller_revenue_sql(project, dataset):
    return f"""
    SELECT COALESCE(SUM(gross_revenue_amount), 0) AS total_reseller_revenue,
           COALESCE(SUM(total_units_sold), 0) AS total_wholesale_units_sold,
           COUNT(*) AS source_rows
    FROM `{project}.{dataset}.revenue_sales_performance`
    WHERE sales_channel = 'Reseller'
      AND (@year IS NULL OR calendar_year = @year)
      AND (@quarter IS NULL OR calendar_quarter_name = @quarter)
      AND (@channel IS NULL OR sales_channel = @channel)
      AND (@category IS NULL OR product_category = @category)
      AND (@subcategory IS NULL OR product_subcategory = @subcategory)
    LIMIT 1
    """


@cache.memoize(timeout=60)
def load_reseller_revenue(
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
            reseller_revenue_sql(project, dataset),
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
    return dict(row)


def wholesale_orders_sql(project, dataset):
    return f"""
    SELECT COUNT(DISTINCT s.sales_order_number) AS wholesale_orders
    FROM `{project}.{dataset}.fct_sales` s
    JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
    LEFT JOIN `{project}.{dataset}.dim_product` p ON s.product_key = p.product_key
    WHERE s.sales_channel = 'Reseller'
      AND s.sales_order_number IS NOT NULL
      AND (@year IS NULL OR d.calendar_year = @year)
      AND (@quarter IS NULL OR d.calendar_quarter_name = @quarter)
      AND (@channel IS NULL OR s.sales_channel = @channel)
      AND (@category IS NULL OR COALESCE(p.category_name, 'Unknown') = @category)
      AND (@subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = @subcategory)
    LIMIT 1
    """


@cache.memoize(timeout=60)
def load_wholesale_orders(
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
            wholesale_orders_sql(project, dataset),
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
    return int(row["wholesale_orders"])


@cache.memoize(timeout=60)
def load_wholesale_comparison(
    project, dataset, year, quarter, channel, category, subcategory
):
    """One cached prior-period snapshot shared by all five YoY badges."""
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
