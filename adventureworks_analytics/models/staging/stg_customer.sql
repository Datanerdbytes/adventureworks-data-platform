with source_data as (
    select * from {{ source('raw_adventureworks', 'dimcustomer') }}
)

select 
    -- 🔑 Primary Key
    cast(customerkey as int64) as customer_key,
    cast(geographykey as int64) as geography_key,

    -- 👤 Demographics & Identifiers
    customeralternatekey as customer_id,
    title,
    firstname as first_name,
    middlename as middle_name,
    lastname as last_name,

    -- 📆 Dates & Status
    cast(birthdate as date) as birth_date,
    case 
        when upper(maritalstatus) = 'M' then 'Married'
        when upper(maritalstatus) = 'S' then 'Single'
        else null 
    end as marital_status,
    case
        when upper(gender) = 'M' then 'Male'
        when upper(gender) = 'F' then 'Female'
        else null 
    end as gender,
    emailaddress as email_address,

    -- 💰 Financial Context
    cast(yearlyincome as float64) as yearly_income,
    cast(totalchildren as int64) as total_children,
    cast(numberchildrenathome as int64) as children_at_home,

    englisheducation as education_level,
    englishoccupation as occupation,

    -- 🏡 Residential Details
    addressline1 as address_line_1,
    addressline2 as address_line_2,
    phone,
    cast(datefirstpurchase as date) as date_first_purchase
from source_data
