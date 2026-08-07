{#
    CI teardown: drop the isolated per-run schema dbt build wrote staging/marts into.
    Invoked via `dbt run-operation drop_ci_schema --args '{schema_name: ...}'` in ci.yml,
    in an `if: always()` step so it runs even if the build/tests failed.
#}
{% macro drop_ci_schema(schema_name) %}
  {% set sql %}
    drop schema if exists {{ schema_name }} cascade
  {% endset %}
  {% do run_query(sql) %}
  {{ log("Dropped CI schema " ~ schema_name, info=true) }}
{% endmacro %}
