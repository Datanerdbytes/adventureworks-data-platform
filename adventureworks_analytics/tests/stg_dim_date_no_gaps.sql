-- Require consecutive days within the loaded range, including leap days.
-- Source membership, row count, and uniqueness tests validate range preservation.
with ordered_dates as (
    select
        calendar_date,
        lag(calendar_date) over (order by calendar_date) as previous_date
    from {{ ref('stg_dim_date') }}
)
{% set date_column = "calendar_date" %}
{% set previous_column = "previous_date" %}
select *
from ordered_dates
where previous_date is not null
  and {{ qe_date_diff(date_column, previous_column, 'DAY') }} != 1
