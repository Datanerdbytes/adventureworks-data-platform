-- Derive expected attributes independently from the calendar date.
-- BigQuery EXTRACT(WEEK) can return zero in January, so use Sunday
-- boundaries since January 1 plus one to match the source convention.
select *
from {{ ref('stg_dim_date') }}
where date_key is distinct from cast(format_date('%Y%m%d', calendar_date) as int64)
   or day_of_week_number is distinct from extract(dayofweek from calendar_date)
   or day_of_week_name is distinct from format_date('%A', calendar_date)
   or day_of_month_number is distinct from extract(day from calendar_date)
   or day_of_year_number is distinct from extract(dayofyear from calendar_date)
   or week_of_year_number is distinct from (
       date_diff(calendar_date, date_trunc(calendar_date, year), week(sunday)) + 1
   )
   or month_name is distinct from format_date('%B', calendar_date)
   or month_number is distinct from extract(month from calendar_date)
   or calendar_quarter is distinct from extract(quarter from calendar_date)
   or calendar_semester is distinct from (
       case when extract(month from calendar_date) <= 6 then 1 else 2 end
   )
   or calendar_year is distinct from extract(year from calendar_date)
