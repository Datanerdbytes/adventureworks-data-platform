/* @datacloud.settings
{
  "version": 1,
  "service": "BIG_QUERY",
  "connectionInfo": {
    "billingProjectId": "INHERIT"
  },
  "dialect": "GOOGLE_SQL"
}
*/

with source_data as (
    select * from {{ source('raw_adventureworks', 'dimdate') }}
)

select
    -- 🔑 Primary Key (Int Smart Date Key, e.g., 20260101)
    cast(datekey as int64) as date_key,

    -- 📅 Calendar Date Primitives
    cast(fulldatealternatekey as date) as calendar_date,
    
    -- Day properties: Sunday = 1 through Saturday = 7.
    cast(daynumberofweek as int64) as day_of_week_number,
    trim(englishdaynameofweek) as day_of_week_name,
    cast(daynumberofmonth as int64) as day_of_month_number,
    cast(daynumberofyear as int64) as day_of_year_number,

    -- Source week numbering: Sunday starts the week; January 1 is in week 1.
    cast(weeknumberofyear as int64) as week_of_year_number,

    -- 🍇 Month Properties
    trim(englishmonthname) as month_name,
    cast(monthnumberofyear as int64) as month_number,

    -- 📊 Quarter Context
    cast(calendarquarter as int64) as calendar_quarter,
    cast(calendarsemester as int64) as calendar_semester,

    -- 📆 Year Tracking
    cast(calendaryear as int64) as calendar_year

from source_data
