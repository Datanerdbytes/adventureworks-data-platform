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


def top_resellers_sql(project, dataset):
    return f"""
    SELECT r.reseller_name, SUM(s.sales_amount) AS revenue
    FROM `{project}.{dataset}.fct_sales` s
    JOIN `{project}.{dataset}.dim_reseller` r ON s.reseller_key = r.reseller_key
    JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
    LEFT JOIN `{project}.{dataset}.dim_product` p ON s.product_key = p.product_key
    WHERE s.sales_channel = 'Reseller'
      AND (@year IS NULL OR d.calendar_year = @year)
      AND (@quarter IS NULL OR d.calendar_quarter_name = @quarter)
      AND (@channel IS NULL OR s.sales_channel = @channel)
      AND (@category IS NULL OR COALESCE(p.category_name, 'Unknown') = @category)
      AND (@subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = @subcategory)
    GROUP BY r.reseller_name
    ORDER BY revenue DESC, r.reseller_name ASC
    LIMIT 10
    """


@cache.memoize(timeout=60)
def load_top_resellers(
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
            top_resellers_sql(project, dataset),
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


def reseller_scatter_sql(project, dataset):
    return f"""
    SELECT r.reseller_key, r.reseller_name, r.annual_revenue,
           SUM(s.order_quantity) AS total_units_sold
    FROM `{project}.{dataset}.fct_sales` s
    JOIN `{project}.{dataset}.dim_reseller` r ON s.reseller_key = r.reseller_key
    JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
    LEFT JOIN `{project}.{dataset}.dim_product` p ON s.product_key = p.product_key
    WHERE s.sales_channel = 'Reseller'
      AND r.annual_revenue IS NOT NULL
      AND (@year IS NULL OR d.calendar_year = @year)
      AND (@quarter IS NULL OR d.calendar_quarter_name = @quarter)
      AND (@channel IS NULL OR s.sales_channel = @channel)
      AND (@category IS NULL OR COALESCE(p.category_name, 'Unknown') = @category)
      AND (@subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = @subcategory)
    GROUP BY r.reseller_key, r.reseller_name, r.annual_revenue
    ORDER BY r.reseller_key
    LIMIT 1001
    """


@cache.memoize(timeout=60)
def load_reseller_scatter(
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
            reseller_scatter_sql(project, dataset),
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


def wholesale_product_mix_sql(project, dataset):
    return f"""
    SELECT product_category, SUM(gross_revenue_amount) AS revenue
    FROM `{project}.{dataset}.revenue_sales_performance`
    WHERE sales_channel = 'Reseller'
      AND (@year IS NULL OR calendar_year = @year)
      AND (@quarter IS NULL OR calendar_quarter_name = @quarter)
      AND (@channel IS NULL OR sales_channel = @channel)
      AND (@category IS NULL OR product_category = @category)
      AND (@subcategory IS NULL OR product_subcategory = @subcategory)
    GROUP BY product_category
    ORDER BY product_category
    LIMIT 1001
    """


@cache.memoize(timeout=60)
def load_wholesale_product_mix(
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
            wholesale_product_mix_sql(project, dataset),
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


def wholesale_operations_sql(project, dataset, staging_dataset):
    return f"""
    WITH invoices AS (
      SELECT s.reseller_key, s.sales_order_number,
             SUM(s.order_quantity) AS units,
             AVG(DATE_DIFF(s.ship_date, s.order_date, DAY)) AS lead_days
      FROM `{project}.{staging_dataset}.stg_fact_reseller_sales` s
      JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
      LEFT JOIN `{project}.{dataset}.dim_product` p ON s.product_key = p.product_key
      WHERE s.sales_order_number IS NOT NULL
        AND (@year IS NULL OR d.calendar_year = @year)
        AND (@quarter IS NULL OR d.calendar_quarter_name = @quarter)
        AND (@channel IS NULL OR @channel = 'Reseller')
        AND (@category IS NULL OR COALESCE(p.category_name, 'Unknown') = @category)
        AND (@subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = @subcategory)
      GROUP BY s.reseller_key, s.sales_order_number
    )
    SELECT r.reseller_key, TRIM(r.reseller_name) AS reseller_name,
           r.order_frequency,
           COUNT(*) AS total_orders_count,
           SUM(i.units) / COUNT(*) AS average_units_per_order,
           AVG(i.lead_days) AS average_shipping_lead_days,
           r.state_province_name, r.country_region_name
    FROM invoices i
    JOIN `{project}.{dataset}.dim_reseller` r ON i.reseller_key = r.reseller_key
    GROUP BY r.reseller_key, r.reseller_name, r.order_frequency,
             r.state_province_name, r.country_region_name
    ORDER BY average_shipping_lead_days DESC, r.reseller_name, r.reseller_key
    LIMIT 1001
    """


@cache.memoize(timeout=60)
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
    with bigquery.Client(project=project) as client:
        job = client.query(
            wholesale_operations_sql(project, dataset, staging_dataset),
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
