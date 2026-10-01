-- Require consecutive days within the loaded range, including leap days.
-- Source membership, row count, and uniqueness tests validate range preservation.
with ordered_dates as (
    select
        calendar_date,
        lag(calendar_date) over (order by calendar_date) as previous_date
    from {{ ref('stg_dim_date') }}
)
select *
from ordered_dates
where previous_date is not null
  and date_diff(calendar_date, previous_date, day) != 1
