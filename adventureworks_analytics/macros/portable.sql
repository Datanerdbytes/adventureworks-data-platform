{#
    Dialect-portable helpers for the analytics models.

    Each macro dispatches on the dbt adapter, so one set of model SQL renders
    either BigQuery SQL (the original warehouse) or DuckDB SQL (the local and
    Vercel build). The bigquery branch reproduces the original SQL verbatim;
    the duckdb branch is the closest DuckDB equivalent of the same operation.
#}

{% macro qe_unsupported_adapter(macro_name) -%}
    {% do exceptions.raise_compiler_error(
        "adventureworks_analytics: macro '" ~ macro_name ~ "' has no implementation for adapter '"
        ~ target.type ~ "'. Supported adapters: bigquery, duckdb."
    ) %}
{%- endmacro %}


{# Non-throwing cast: NULL on malformed input. #}
{% macro qe_safe_cast(expression, type) -%}
    {{ return(adapter.dispatch('qe_safe_cast')(expression, type)) }}
{%- endmacro %}
{% macro bigquery__qe_safe_cast(expression, type) -%}
    SAFE_CAST({{ expression }} AS {{ type }})
{%- endmacro %}

{% macro duckdb__qe_safe_cast(expression, type) -%}
    TRY_CAST({{ expression }} AS {{ type }})
{%- endmacro %}

{% macro default__qe_safe_cast(expression, type) -%}
    {{ qe_unsupported_adapter('qe_safe_cast') }}
{%- endmacro %}


{# Text type name: BigQuery spells it string, DuckDB spells it VARCHAR. #}
{% macro qe_string_type() -%}
    {{ return(adapter.dispatch('qe_string_type')()) }}
{%- endmacro %}

{% macro bigquery__qe_string_type() -%}
    string
{%- endmacro %}

{% macro duckdb__qe_string_type() -%}
    VARCHAR
{%- endmacro %}

{% macro default__qe_string_type() -%}
    {{ qe_unsupported_adapter('qe_string_type') }}
{%- endmacro %}


{# DuckDB rejects the call form of the current-time functions. #}
{% macro qe_current_timestamp() -%}
    {{ return(adapter.dispatch('qe_current_timestamp')()) }}
{%- endmacro %}

{% macro bigquery__qe_current_timestamp() -%}
    CURRENT_TIMESTAMP()
{%- endmacro %}

{% macro duckdb__qe_current_timestamp() -%}
    current_timestamp
{%- endmacro %}

{% macro default__qe_current_timestamp() -%}
    {{ qe_unsupported_adapter('qe_current_timestamp') }}
{%- endmacro %}


{% macro qe_current_date() -%}
    {{ return(adapter.dispatch('qe_current_date')()) }}
{%- endmacro %}

{% macro bigquery__qe_current_date() -%}
    CURRENT_DATE()
{%- endmacro %}

{% macro duckdb__qe_current_date() -%}
    current_date
{%- endmacro %}

{% macro default__qe_current_date() -%}
    {{ qe_unsupported_adapter('qe_current_date') }}
{%- endmacro %}


{# BigQuery orders DATE_DIFF as (end, start, unit); DuckDB as (unit, start, end).
    Both engines count unit boundaries crossed, so the results agree. #}
{% macro qe_date_diff(end_expression, start_expression, unit) -%}
    {{ return(adapter.dispatch('qe_date_diff')(end_expression, start_expression, unit)) }}
{%- endmacro %}

{% macro bigquery__qe_date_diff(end_expression, start_expression, unit) -%}
    DATE_DIFF({{ end_expression }}, {{ start_expression }}, {{ unit }})
{%- endmacro %}

{% macro duckdb__qe_date_diff(end_expression, start_expression, unit) -%}
    date_diff('{{ unit | lower }}', {{ start_expression }}, {{ end_expression }})
{%- endmacro %}

{% macro default__qe_date_diff(end_expression, start_expression, unit) -%}
    {{ qe_unsupported_adapter('qe_date_diff') }}
{%- endmacro %}


{# BigQuery SAFE_DIVIDE returns NULL for a zero divisor; DuckDB fdiv returns inf. #}
{% macro qe_safe_divide(numerator, denominator) -%}
    {{ return(adapter.dispatch('qe_safe_divide')(numerator, denominator)) }}
{%- endmacro %}

{% macro bigquery__qe_safe_divide(numerator, denominator) -%}
    SAFE_DIVIDE({{ numerator }}, {{ denominator }})
{%- endmacro %}

{% macro duckdb__qe_safe_divide(numerator, denominator) -%}
    CASE
        WHEN {{ denominator }} = 0 THEN NULL
        ELSE {{ numerator }} / {{ denominator }}
    END
{%- endmacro %}

{% macro default__qe_safe_divide(numerator, denominator) -%}
    {{ qe_unsupported_adapter('qe_safe_divide') }}
{%- endmacro %}


{# Date formatting with C-style tokens that both engines spell identically. #}
{% macro qe_format_date(format, expression) -%}
    {{ return(adapter.dispatch('qe_format_date')(format, expression)) }}
{%- endmacro %}

{% macro bigquery__qe_format_date(format, expression) -%}
    FORMAT_DATE('{{ format }}', {{ expression }})
{%- endmacro %}

{% macro duckdb__qe_format_date(format, expression) -%}
    strftime({{ expression }}, '{{ format }}')
{%- endmacro %}

{% macro default__qe_format_date(format, expression) -%}
    {{ qe_unsupported_adapter('qe_format_date') }}
{%- endmacro %}


{# BigQuery's DAYOFWEEK numbers days 1..7 with Sunday = 1. DuckDB's
    dayofweek is Monday-based, but strftime '%w' gives 0 = Sunday .. 6 =
    Saturday, so adding one reproduces the BigQuery numbering exactly. #}
{% macro qe_day_of_week_sunday_first(expression) -%}
    {{ return(adapter.dispatch('qe_day_of_week_sunday_first')(expression)) }}
{%- endmacro %}

{% macro bigquery__qe_day_of_week_sunday_first(expression) -%}
    EXTRACT(DAYOFWEEK FROM {{ expression }})
{%- endmacro %}

{% macro duckdb__qe_day_of_week_sunday_first(expression) -%}
    (CAST(strftime({{ expression }}, '%w') AS INTEGER) + 1)
{%- endmacro %}

{% macro default__qe_day_of_week_sunday_first(expression) -%}
    {{ qe_unsupported_adapter('qe_day_of_week_sunday_first') }}
{%- endmacro %}


{# Week-of-year whose weeks start on Sunday and week 1 opens on January 1.
    BigQuery counts Sunday-start week boundaries crossed since January 1.
    DuckDB weeks start on Monday and strftime('%w') gives 0 = Sunday, so the
    equivalent counts Sundays strictly after January 1 up to the date: the
    first crossing lands on January 1 + step days (step is 7 when January 1
    is itself a Sunday, since that Sunday opens week 1 instead of crossing
    into a second week), then one further boundary for each full week. #}
{% macro qe_week_of_year_sunday_start(expression) -%}
    {{ return(adapter.dispatch('qe_week_of_year_sunday_start')(expression)) }}
{%- endmacro %}

{% macro bigquery__qe_week_of_year_sunday_start(expression) -%}
    (DATE_DIFF({{ expression }}, date_trunc({{ expression }}, year), week(sunday)) + 1)
{%- endmacro %}

{% macro duckdb__qe_week_of_year_sunday_start(expression) -%}
    (case
        when cast({{ expression }} - cast(date_trunc('year', {{ expression }}) as date) as integer)
            < (case when (7 - cast(strftime(cast(date_trunc('year', {{ expression }}) as date), '%w') as integer)) % 7 = 0
                    then 7
                    else (7 - cast(strftime(cast(date_trunc('year', {{ expression }}) as date), '%w') as integer)) % 7 end)
        then 1
        else 2 + floor((
            cast({{ expression }} - cast(date_trunc('year', {{ expression }}) as date) as integer)
            - (case when (7 - cast(strftime(cast(date_trunc('year', {{ expression }}) as date), '%w') as integer)) % 7 = 0
                    then 7
                    else (7 - cast(strftime(cast(date_trunc('year', {{ expression }}) as date), '%w') as integer)) % 7 end)
        ) / 7)
    end)
{%- endmacro %}


{# One day subtracted from a date: BigQuery's DATE_SUB(date, INTERVAL 1 DAY).
    DuckDB's date-minus-interval returns TIMESTAMP, so the branch casts back to
    DATE to keep the column type identical on both engines. #}
{% macro qe_date_sub_day(expression) -%}
    {{ return(adapter.dispatch('qe_date_sub_day')(expression)) }}
{%- endmacro %}

{% macro bigquery__qe_date_sub_day(expression) -%}
    DATE_SUB({{ expression }}, INTERVAL 1 DAY)
{%- endmacro %}

{% macro duckdb__qe_date_sub_day(expression) -%}
    CAST({{ expression }} - INTERVAL 1 DAY AS DATE)
{%- endmacro %}

{% macro default__qe_date_sub_day(expression) -%}
    {{ qe_unsupported_adapter('qe_date_sub_day') }}
{%- endmacro %}


{# NaN and infinity guard for float64 money columns. BigQuery spells them
    is_nan/is_inf, DuckDB spells them isnan/isinf; NULL passes through both
    call forms as NULL, and ordinary doubles stay true. #}
{% macro qe_finite_double(columns) -%}
    {{ return(adapter.dispatch('qe_finite_double')(columns)) }}
{%- endmacro %}

{% macro bigquery__qe_finite_double(columns) -%}
    {% set checks = [] %}
    {% for column in columns -%}
        {% do checks.append("not is_nan(" ~ column ~ ") and not is_inf(" ~ column ~ ")") %}
    {%- endfor %}
    {{ checks | join(" and ") }}
{%- endmacro %}

{% macro duckdb__qe_finite_double(columns) -%}
    {% set checks = [] %}
    {% for column in columns -%}
        {% do checks.append("not isnan(" ~ column ~ ") and not isinf(" ~ column ~ ")") %}
    {%- endfor %}
    {{ checks | join(" and ") }}
{%- endmacro %}

{% macro default__qe_finite_double(columns) -%}
    {{ qe_unsupported_adapter('qe_finite_double') }}
{%- endmacro %}

{# Email-shape containment against a POSIX regular expression. BigQuery's
    regexp_contains scans the whole string; DuckDB's regexp_matches needs the
    match inside the full string, which the .* wrapping reproduces. A NULL
    email contains nothing, matching the BigQuery operator. #}
{% macro qe_regexp_contains(expression, pattern) -%}
    {{ return(adapter.dispatch('qe_regexp_contains')(expression, pattern)) }}
{%- endmacro %}

{% macro bigquery__qe_regexp_contains(expression, pattern) -%}
    REGEXP_CONTAINS({{ expression }}, r'{{ pattern }}')
{%- endmacro %}

{% macro duckdb__qe_regexp_contains(expression, pattern) -%}
    regexp_full_match({{ expression }}, '{{ pattern }}')
    {# Callers pass a fully anchored pattern; the sole caller (the email
       shape check) does, so a full-string match equals BigQuery contains
       over an anchored regex. #}
{%- endmacro %}

{% macro default__qe_regexp_contains(expression, pattern) -%}
    {{ qe_unsupported_adapter('qe_regexp_contains') }}
{%- endmacro %}
