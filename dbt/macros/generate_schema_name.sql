{#
    Standard dbt override: a model/seed's `+schema` config becomes the LITERAL schema name,
    not `<target_schema>_<custom_schema>` (dbt's default, which would turn our `raw`/`staging`/
    `marts` configs into e.g. `main_raw` on the duckdb target). Without this, sources.yml's
    `schema: raw` wouldn't resolve to where `dbt seed` actually lands the fixture data.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
