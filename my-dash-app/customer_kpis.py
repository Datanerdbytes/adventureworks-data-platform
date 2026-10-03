"""Filter-aware customer metrics at customer/order grain.

The demographic mart supplies the geographic mapping contract and the growth
mart supplies calendar/channel semantics. Neither retains customer IDs or
customer-state/month grain, so compute non-additive KPIs from their source facts.
"""

from google.cloud import bigquery
from revenue_kpis import cache, filter_parameters


def customer_scorecards_sql(project, dataset):
    return f"""
    WITH history AS (
      SELECT s.customer_key, s.sales_channel, s.sales_order_number,
             d.calendar_date AS order_date, d.calendar_year, d.calendar_quarter_name,
             s.sales_amount,
             COALESCE(NULLIF(TRIM(c.state_province_name), ''), 'Unknown') AS state,
             COALESCE(NULLIF(TRIM(c.country_region_name), ''), 'Unknown') AS country,
             COALESCE(NULLIF(TRIM(t.territory_group), ''), 'Unknown') AS territory,
             COALESCE(p.category_name, 'Unknown') AS category,
             COALESCE(p.subcategory_name, 'Unknown') AS subcategory
      FROM `{project}.{dataset}.fct_sales` s
      JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
      LEFT JOIN `{project}.{dataset}.dim_customer` c ON s.customer_key = c.customer_key
      LEFT JOIN `{project}.{dataset}.dim_product` p ON s.product_key = p.product_key
      LEFT JOIN `{project}.{dataset}.dim_sales_territory` t
        ON s.sales_territory_key = t.sales_territory_key
    ), scoped AS (
      SELECT * FROM history
      WHERE (@channel IS NULL OR sales_channel = @channel)
        AND (@category IS NULL OR category = @category)
        AND (@subcategory IS NULL OR subcategory = @subcategory)
    ), selected AS (
      SELECT * FROM scoped
      WHERE (@year IS NULL OR calendar_year = @year)
        AND (@quarter IS NULL OR calendar_quarter_name = @quarter)
    ), reporting_dates AS (
      SELECT MAX(order_date) AS latest_selected FROM history
      WHERE (@year IS NULL OR calendar_year = @year)
        AND (@quarter IS NULL OR calendar_quarter_name = @quarter)
    ), cutoff AS (
      SELECT LEAST(
        (SELECT MAX(order_date) FROM history),
        CASE WHEN @quarter IS NOT NULL THEN LAST_DAY(latest_selected, QUARTER)
             WHEN @year IS NOT NULL THEN LAST_DAY(latest_selected, YEAR)
             ELSE latest_selected END
      ) AS as_of FROM reporting_dates
    ), acquired AS (
      SELECT c.customer_key, COALESCE(c.date_first_purchase, MIN(h.order_date)) AS acquired_on
      FROM `{project}.{dataset}.dim_customer` c
      LEFT JOIN history h ON c.customer_key = h.customer_key AND h.sales_channel = 'Internet'
      GROUP BY c.customer_key, c.date_first_purchase
    ), cohort AS (
      SELECT DISTINCT a.customer_key, a.acquired_on FROM acquired a CROSS JOIN cutoff
      WHERE a.acquired_on <= as_of AND (@channel IS NULL OR @channel = 'Internet')
        AND ((@category IS NULL AND @subcategory IS NULL) OR EXISTS (
          SELECT 1 FROM scoped s WHERE s.customer_key = a.customer_key
            AND s.sales_channel = 'Internet' AND s.order_date <= as_of))
    ), last_orders AS (
      SELECT c.customer_key, COALESCE(MAX(h.order_date), c.acquired_on) AS last_order
      FROM cohort c CROSS JOIN cutoff LEFT JOIN history h ON c.customer_key = h.customer_key
        AND h.sales_channel = 'Internet' AND h.order_date <= as_of
      GROUP BY c.customer_key, c.acquired_on
    ), territories AS (
      SELECT territory, SUM(sales_amount) AS revenue FROM selected GROUP BY 1
    ), state_orders AS (
      SELECT state, country,
        COUNT(DISTINCT IF(DATE_TRUNC(order_date, MONTH) = DATE_TRUNC(as_of, MONTH),
          sales_order_number, NULL)) AS current_orders,
        COUNT(DISTINCT IF(DATE_TRUNC(order_date, MONTH) = DATE_SUB(DATE_TRUNC(as_of, MONTH), INTERVAL 1 MONTH),
          sales_order_number, NULL)) AS previous_orders
      FROM scoped CROSS JOIN cutoff
      WHERE sales_channel = 'Internet' AND customer_key IS NOT NULL AND state != 'Unknown'
        AND order_date BETWEEN DATE_SUB(DATE_TRUNC(as_of, MONTH), INTERVAL 1 MONTH) AND as_of
      GROUP BY 1, 2
    ), state_baseline AS (
      SELECT EXISTS (SELECT 1 FROM history CROSS JOIN cutoff
        WHERE sales_channel = 'Internet'
          AND DATE_TRUNC(order_date, MONTH) = DATE_SUB(DATE_TRUNC(as_of, MONTH), INTERVAL 1 MONTH)) AS available
    ), state_growth AS (
      SELECT *, current_orders - previous_orders AS increase FROM state_orders
      WHERE current_orders > previous_orders
        AND (SELECT available FROM state_baseline)
    )
    SELECT (SELECT COUNT(*) FROM selected) AS matching_rows,
      (SELECT available FROM state_baseline) AS state_baseline_available,
      (SELECT COUNT(*) FROM cohort) AS customers,
      (SELECT COALESCE(SUM(s.sales_amount), 0) FROM scoped s JOIN cohort c USING (customer_key)
        WHERE s.sales_channel = 'Internet' AND s.order_date <= (SELECT as_of FROM cutoff)) AS customer_revenue,
      (SELECT COUNTIF(DATE_DIFF(as_of, last_order, DAY) > 180) FROM last_orders CROSS JOIN cutoff) AS dormant,
      (SELECT as_of FROM cutoff) AS as_of,
      (SELECT AS STRUCT territory, revenue FROM territories ORDER BY revenue DESC, territory LIMIT 1) AS top_territory,
      (SELECT AS STRUCT state, country, increase, current_orders, previous_orders FROM state_growth
        ORDER BY increase DESC, state, country LIMIT 1) AS top_state
    LIMIT 1
    """


@cache.memoize(timeout=60)
def load_customer_scorecards(
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
            customer_scorecards_sql(project, dataset),
            job_config=bigquery.QueryJobConfig(
                query_parameters=filter_parameters(
                    year, quarter, channel, category, subcategory
                ),
                maximum_bytes_billed=100 * 1024 * 1024,
                use_query_cache=True,
            ),
        )
        try:
            return dict(next(iter(job.result(timeout=20))))
        except TimeoutError:
            job.cancel()
            raise
