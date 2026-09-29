{% test no_unwanted_spaces(model, column_name) %}

with validation_errors as (

    select
        {{ column_name }} as invalid_value
    from {{ model }}
    where 
        -- Catches leading or trailing spaces
        {{ column_name }} != trim({{ column_name }})
        -- Optional: Catches double/multiple consecutive middle spaces (e.g., 'John  Doe')
        or {{ column_name }} like '%  %'

)

select *
from validation_errors

{% endtest %}