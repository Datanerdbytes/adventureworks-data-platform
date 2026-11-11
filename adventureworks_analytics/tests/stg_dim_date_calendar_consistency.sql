-- Derive expected attributes independently from the calendar date.
-- BigQuery EXTRACT(WEEK) can return zero in January, so use Sunday
-- boundaries since January 1 plus one to match the source convention.
select *
from {{ ref('stg_dim_date') }}
{% set calendar_column = "calendar_date" %}
where date_key is distinct from cast({{ qe_format_date('%Y%m%d', calendar_column) }} as bigint)
   or day_of_week_number is distinct from {{ qe_day_of_week_sunday_first(calendar_column) }}
   or day_of_week_name is distinct from {{ qe_format_date('%A', calendar_column) }}
   or day_of_month_number is distinct from extract(day from calendar_date)
   or day_of_year_number is distinct from extract(dayofyear from calendar_date)
   or week_of_year_number is distinct from {{ qe_week_of_year_sunday_start(calendar_column) }}
   or month_name is distinct from {{ qe_format_date('%B', calendar_column) }}
   or month_number is distinct from extract(month from calendar_date)
   or calendar_quarter is distinct from extract(quarter from calendar_date)
   or calendar_semester is distinct from (
       case when extract(month from calendar_date) <= 6 then 1 else 2 end
   )
   or calendar_year is distinct from extract(year from calendar_date)
