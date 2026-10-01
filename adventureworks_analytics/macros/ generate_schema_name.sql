{% macro generate_schema_name(custom_schema_name, node) -%}
    {# 
       If a custom schema parameter is explicitly specified (like 'gold'),
       this block forces dbt to drop the default target dataset prefix completely.
       Minnie-malist naming standard for production clarity
    #}
    {%- if custom_schema_name is not none -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ target.schema }}
    {%- endif -%}
{%- endmacro %}
