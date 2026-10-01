{% test date_continuity(model, column_name) %}
-- Calendar arithmetic handles month/year boundaries and leap days.
-- Separate not-null, uniqueness, and source-coverage tests protect the grain
-- and detect missing dates at either end of the loaded range.
with ordered_dates as (
    select
        {{ column_name }} as calendar_date,
        lag({{ column_name }}) over (order by {{ column_name }}) as previous_date
    from {{ model }}
)
select *
from ordered_dates
where previous_date is not null
  and date_diff(calendar_date, previous_date, day) != 1
{% endtest %}
