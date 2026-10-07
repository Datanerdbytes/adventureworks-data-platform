"""Filter-aware customer metrics at customer/order grain.

The demographic mart supplies the geographic mapping contract and the growth
mart supplies calendar/channel semantics. Neither retains customer IDs or
customer-state/month grain, so compute non-additive KPIs from their source facts.
"""

from google.cloud import bigquery
from revenue_kpis import cache, filter_parameters


def customer_cohort_ctes(project, dataset):
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
    )
    """


def customer_scorecards_sql(project, dataset):
    return customer_cohort_ctes(project, dataset) + f""", last_orders AS (
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


def customer_demographics_sql(project, dataset):
    return f"""
    WITH dates AS (
      SELECT MAX(d.calendar_date) AS as_of
      FROM `{project}.{dataset}.fct_sales` s
      JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
      WHERE (@year IS NULL OR d.calendar_year = @year)
        AND (@quarter IS NULL OR d.calendar_quarter_name = @quarter)
    ), customers AS (
      SELECT DISTINCT s.customer_key,
        COALESCE(NULLIF(TRIM(c.country_region_name), ''), 'Unknown') AS region,
        c.birth_date, dates.as_of
      FROM `{project}.{dataset}.fct_sales` s
      JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
      LEFT JOIN `{project}.{dataset}.dim_customer` c ON s.customer_key = c.customer_key
      LEFT JOIN `{project}.{dataset}.dim_product` p ON s.product_key = p.product_key
      CROSS JOIN dates
      WHERE s.sales_channel = 'Internet' AND s.customer_key IS NOT NULL
        AND (@channel IS NULL OR s.sales_channel = @channel)
        AND (@year IS NULL OR d.calendar_year = @year)
        AND (@quarter IS NULL OR d.calendar_quarter_name = @quarter)
        AND (@category IS NULL OR COALESCE(p.category_name, 'Unknown') = @category)
        AND (@subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = @subcategory)
    ), ages AS (
      SELECT *, DATE_DIFF(as_of, birth_date, YEAR) -
        IF(FORMAT_DATE('%m%d', as_of) < FORMAT_DATE('%m%d', birth_date), 1, 0) AS age
      FROM customers
    )
    SELECT region,
      CASE WHEN age IS NULL OR age < 0 OR age > 120 THEN 'Unknown'
           WHEN age < 18 THEN 'Under 18'
           WHEN age < 30 THEN '18–29'
           WHEN age < 45 THEN '30–44'
           WHEN age < 60 THEN '45–59' ELSE '60+' END AS age_group,
      COUNT(DISTINCT customer_key) AS customers, MAX(as_of) AS as_of
    FROM ages GROUP BY 1, 2 ORDER BY 1, 2 LIMIT 1001
    """


@cache.memoize(timeout=60)
def load_customer_demographics(
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
            customer_demographics_sql(project, dataset),
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
    if len(rows) > 1000:
        raise ValueError("Demographic result exceeds supported range")
    return rows


def customer_map_sql(project, dataset, use_mart=False):
    if use_mart:
        return f"""SELECT territory_group, territory_country AS country,
          customer_state_province AS state, SUM(gross_revenue_amount) AS revenue
          FROM `{project}.{dataset}.marts_demographic_regional_insights`
          WHERE (@channel IS NULL OR sales_channel = @channel)
          GROUP BY 1,2,3 ORDER BY 1,2,3 LIMIT 2001"""
    return f"""SELECT t.territory_group, t.territory_country AS country,
      CASE WHEN s.sales_channel = 'Reseller' THEN 'Wholesale/Reseller'
           ELSE COALESCE(NULLIF(TRIM(c.state_province_name), ''), 'Unknown') END AS state,
      SUM(s.sales_amount) AS revenue
      FROM `{project}.{dataset}.fct_sales` s
      JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
      JOIN `{project}.{dataset}.dim_sales_territory` t ON s.sales_territory_key = t.sales_territory_key
      LEFT JOIN `{project}.{dataset}.dim_customer` c ON s.customer_key = c.customer_key
      LEFT JOIN `{project}.{dataset}.dim_product` p ON s.product_key = p.product_key
      WHERE (@year IS NULL OR d.calendar_year = @year)
        AND (@quarter IS NULL OR d.calendar_quarter_name = @quarter)
        AND (@channel IS NULL OR s.sales_channel = @channel)
        AND (@category IS NULL OR COALESCE(p.category_name, 'Unknown') = @category)
        AND (@subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = @subcategory)
      GROUP BY 1,2,3 ORDER BY 1,2,3 LIMIT 2001"""


@cache.memoize(timeout=60)
def load_customer_map(
    project,
    dataset,
    year=None,
    quarter=None,
    channel=None,
    category=None,
    subcategory=None,
):
    from google.api_core.exceptions import NotFound

    with bigquery.Client(project=project) as client:
        use_mart = all(
            value is None for value in (year, quarter, category, subcategory)
        )
        if use_mart:
            try:
                client.get_table(
                    f"{project}.{dataset}.marts_demographic_regional_insights"
                )
            except NotFound:
                use_mart = False
        job = client.query(
            customer_map_sql(project, dataset, use_mart),
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
    if len(rows) > 2000:
        raise ValueError("Too many geographic segments")
    return rows


def customer_lifecycle_sql(project, dataset):
    return customer_cohort_ctes(project, dataset) + """,
    activity AS (
      SELECT c.customer_key, cutoff.as_of,
        COALESCE(MAX(h.order_date), c.acquired_on) AS last_order,
        COUNT(DISTINCT h.sales_order_number) AS orders
      FROM cohort c CROSS JOIN cutoff
      LEFT JOIN history h ON c.customer_key = h.customer_key
        AND h.sales_channel = 'Internet' AND h.order_date <= cutoff.as_of
      GROUP BY c.customer_key, c.acquired_on, cutoff.as_of
    ), lifecycle AS (
      SELECT customer_key, as_of,
        CASE WHEN DATE_DIFF(as_of, last_order, DAY) > 180 THEN 'Dormant'
             WHEN DATE_DIFF(as_of, last_order, DAY) > 90 THEN 'Slipping Account'
             WHEN orders > 1 THEN 'Active Repeat'
             ELSE 'New Cohort' END AS stage
      FROM activity
    )
    SELECT stage, COUNT(DISTINCT customer_key) AS customers, MAX(as_of) AS as_of
    FROM lifecycle GROUP BY stage LIMIT 4
    """


@cache.memoize(timeout=60)
def load_customer_lifecycle(
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
            customer_lifecycle_sql(project, dataset),
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


DEMOGRAPHIC_DIMENSIONS = {
    "income": """CASE WHEN c.yearly_income IS NULL THEN 'Unknown'
        WHEN c.yearly_income < 30000 THEN 'Low Income (<30k)'
        WHEN c.yearly_income < 70000 THEN 'Middle Income (30k-70k)'
        WHEN c.yearly_income < 100000 THEN 'High Income (70k-100k)'
        ELSE 'Very High Income (100k+)' END""",
    "occupation": "COALESCE(NULLIF(TRIM(c.occupation), ''), 'Unknown')",
    "education": "COALESCE(NULLIF(TRIM(c.education_level), ''), 'Unknown')",
}


def customer_segment_revenue_sql(project, dataset, dimension):
    # Only server-owned expressions may enter SQL; never interpolate a UI value.
    expression = DEMOGRAPHIC_DIMENSIONS[dimension]
    return f"""SELECT {expression} AS segment, SUM(s.sales_amount) AS revenue
      FROM `{project}.{dataset}.fct_sales` s
      JOIN `{project}.{dataset}.dim_date` d ON s.order_date_key = d.date_key
      LEFT JOIN `{project}.{dataset}.dim_customer` c ON s.customer_key = c.customer_key
      LEFT JOIN `{project}.{dataset}.dim_product` p ON s.product_key = p.product_key
      WHERE s.sales_channel = 'Internet' AND s.customer_key IS NOT NULL
        AND (@channel IS NULL OR s.sales_channel = @channel)
        AND (@year IS NULL OR d.calendar_year = @year)
        AND (@quarter IS NULL OR d.calendar_quarter_name = @quarter)
        AND (@category IS NULL OR COALESCE(p.category_name, 'Unknown') = @category)
        AND (@subcategory IS NULL OR COALESCE(p.subcategory_name, 'Unknown') = @subcategory)
      GROUP BY 1 ORDER BY revenue DESC, segment LIMIT 101"""


@cache.memoize(timeout=60)
def load_customer_segment_revenue(
    project,
    dataset,
    dimension,
    year=None,
    quarter=None,
    channel=None,
    category=None,
    subcategory=None,
):
    with bigquery.Client(project=project) as client:
        job = client.query(
            customer_segment_revenue_sql(project, dataset, dimension),
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
    if len(rows) > 100:
        raise ValueError("Too many demographic segments")
    return rows


def customer_ledger_sql(project, dataset):
    income = DEMOGRAPHIC_DIMENSIONS["income"]
    return customer_cohort_ctes(project, dataset) + f""",
    country_groups AS (
      SELECT territory_country AS country,
        CASE WHEN COUNT(DISTINCT territory_group) = 1 THEN MIN(territory_group)
             ELSE 'Unknown' END AS territory
      FROM `{project}.{dataset}.dim_sales_territory` GROUP BY 1
    ), customer_sales AS (
      SELECT s.customer_key, SUM(s.sales_amount) AS revenue,
        COUNT(DISTINCT s.sales_order_number) AS orders
      FROM scoped s CROSS JOIN cutoff
      WHERE s.sales_channel = 'Internet' AND s.order_date <= as_of GROUP BY 1
    ), last_activity AS (
      SELECT h.customer_key, MAX(h.order_date) AS last_order
      FROM history h CROSS JOIN cutoff
      WHERE h.sales_channel = 'Internet' AND h.order_date <= as_of GROUP BY 1
    ), profiles AS (
      SELECT a.customer_key,
        COALESCE(NULLIF(TRIM(c.state_province_name), ''), 'Unknown') AS state,
        COALESCE(NULLIF(TRIM(c.country_region_name), ''), 'Unknown') AS country,
        COALESCE(g.territory, 'Unknown') AS territory,
        {income} AS income,
        COALESCE(NULLIF(TRIM(c.occupation), ''), 'Unknown') AS occupation,
        COALESCE(s.revenue, 0) AS revenue, COALESCE(s.orders, 0) AS orders,
        CASE WHEN DATE_DIFF(as_of, COALESCE(l.last_order, a.acquired_on), DAY) > 180
             THEN 1 ELSE 0 END AS dormant,
        cutoff.as_of
      FROM cohort a JOIN `{project}.{dataset}.dim_customer` c USING (customer_key)
      CROSS JOIN cutoff
      LEFT JOIN country_groups g ON TRIM(c.country_region_name) = g.country
      LEFT JOIN customer_sales s USING (customer_key)
      LEFT JOIN last_activity l USING (customer_key)
    ), income_counts AS (
      SELECT country, state, income, COUNT(*) AS profiles FROM profiles GROUP BY 1,2,3
    ), income_ranked AS (
      SELECT *, ROW_NUMBER() OVER (PARTITION BY country, state
        ORDER BY profiles DESC, CASE WHEN income = 'Unknown' THEN 1 ELSE 0 END, income) AS rank
      FROM income_counts
    ), occupation_counts AS (
      SELECT country, state, occupation, COUNT(*) AS profiles FROM profiles GROUP BY 1,2,3
    ), occupation_ranked AS (
      SELECT *, ROW_NUMBER() OVER (PARTITION BY country, state
        ORDER BY profiles DESC, CASE WHEN occupation = 'Unknown' THEN 1 ELSE 0 END, occupation) AS rank
      FROM occupation_counts
    ), regional AS (
      SELECT country, state, territory, COUNT(DISTINCT customer_key) AS customers,
        SUM(revenue) AS revenue, SUM(orders) / COUNT(DISTINCT customer_key) AS average_orders,
        SUM(dormant) AS dormant, MAX(as_of) AS as_of
      FROM profiles GROUP BY 1,2,3
    )
    SELECT r.*, i.income AS dominant_income, o.occupation AS top_occupation
    FROM regional r
    JOIN income_ranked i ON r.country = i.country AND r.state = i.state AND i.rank = 1
    JOIN occupation_ranked o ON r.country = o.country AND r.state = o.state AND o.rank = 1
    ORDER BY revenue DESC, country, state LIMIT 1001
    """


@cache.memoize(timeout=60)
def load_customer_ledger(
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
            customer_ledger_sql(project, dataset),
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
    if len(rows) > 1000:
        raise ValueError("Too many regional ledger rows")
    return rows
