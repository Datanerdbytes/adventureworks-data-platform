with staged_date as (
    select * from {{ ref('stg_dim_date') }}
)

select
    -- 🔑 Primary Key (Int Smart Date Key, e.g., 20260101)
    date_key,

    -- 📅 Calendar Date Primitives
    calendar_date,
    
    -- 🗓️ Day Properties
    day_of_week_number,
    day_of_week_name,
    day_of_month_number,
    day_of_year_number,

    -- ⏱️ Week Tracking
    week_of_year_number,

    -- 🍇 Month Properties
    month_name,
    month_number,

    -- 📊 Quarter & Semester Context
    calendar_quarter,
    'Q' || cast(calendar_quarter as string) as calendar_quarter_name, -- e.g., 'Q1', 'Q2'
    calendar_semester,

    -- 📆 Year Tracking
    calendar_year,

    -- 🛡️ BUSINESS REPORTING FLAGS
    -- Instantly isolates weekends without forcing BI tools to calculate day numbers dynamically
    case 
        when day_of_week_number in (1, 7) then true 
        else false 
    end as is_weekend_flag

from staged_date
