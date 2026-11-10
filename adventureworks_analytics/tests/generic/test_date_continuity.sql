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
{% set date_column = "calendar_date" %}
{% set previous_column = "previous_date" %}
select *
from ordered_dates
where previous_date is not null
  and {{ qe_date_diff(date_column, previous_column, 'DAY') }} != 1
{% endtest %}
