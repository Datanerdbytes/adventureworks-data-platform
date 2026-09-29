with raw_products as (
    select * from {{ source('raw_adventureworks', 'dimproduct') }}
),

raw_subcategories as (
    select * from {{ source('raw_adventureworks', 'dimproductsubcategory') }}
),

raw_categories as (
    select * from {{ source('raw_adventureworks', 'dimproductcategory') }}
)

select
    -- 🔑 Primary & Foreign Keys
    cast(p.productkey as int64) as product_key,
    cast(p.productsubcategorykey as int64) as product_subcategory_key,
    cast(s.productcategorykey as int64) as product_category_key,

    -- 🏷️ Identifiers & Codes
    p.productalternatekey as product_id,
    p.englishproductname as product_name,
    p.color,
    p.size,
    p.sizeunitmeasurecode as size_unit_measure_code,
    p.weightunitmeasurecode as weight_unit_measure_code,

    -- 📊 Inventory Specifications
    cast(p.weight as float64) as weight,
    case 
        when upper(trim(p.productline)) = 'M'  then 'Mountain'
        when upper(trim(p.productline)) = 'R'  then 'Road'
        when upper(trim(p.productline)) = 'T'  then 'Touring'
        when upper(trim(p.productline)) = 'S'  then 'Components'  
    else 'Unknown'
    end as product_line,
    case 
        when upper(trim(p.class)) = 'L' then 'Low'
        when upper(trim(p.class)) = 'M' then 'Medium'
        when upper(trim(p.class)) = 'H' then 'High'
    else 'Unknown'
    end as class,
    
    case
        when upper(trim(p.style)) = 'U' then 'Universal'
        when upper(trim(p.style)) = 'W' then 'Women'
        when upper(trim(p.style)) = 'M' then 'Men'
    else 'Unknown'
    end as style,
    p.modelname as model_name,

    -- 💰 Financial Context
    cast(p.standardcost as float64) as standard_cost,
    cast(p.listprice as float64) as list_price,

    -- 🛠️ Statuses & Flags
    case 
        when p.finishedgoodsflag is true then 'Finished Good'
        else 'Component/Raw Material'
    end as product_status,
    
    p.status as current_status,

    -- 📆 Product Timeline Tracking
    cast(p.startdate as date) as valid_from_date,
    cast(p.enddate as date) as valid_to_date,

    -- 📂 Denormalized Category Hierarchy Boundaries
    s.englishproductsubcategoryname as subcategory_name,
    c.englishproductcategoryname as category_name

from raw_products p
left join raw_subcategories s 
    on p.productsubcategorykey = s.productsubcategorykey
left join raw_categories c 
    on s.productcategorykey = c.productcategorykey