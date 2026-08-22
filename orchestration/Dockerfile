# Extends the stock Airflow image with this project's own runtime deps (requests,
# psycopg, SQLAlchemy, snowflake-sqlalchemy) plus dbt, so DAG tasks can `import ingest`,
# `import config`, etc. directly and the snowflake_dbt_pipeline DAG can shell out to a
# `dbt` binary that's actually on PATH -- no separate dbt container to coordinate.
ARG AIRFLOW_IMAGE_NAME=apache/airflow:3.3.0
FROM ${AIRFLOW_IMAGE_NAME}

# Mirrors the real repo layout (dbt-versions.txt at the root, requirements-airflow.txt
# under orchestration/) so that file's `-r ../dbt-versions.txt` resolves the same way
# here as it does for a plain `pip install` from a checked-out clone.
COPY requirements.txt dbt-versions.txt /tmp/
COPY orchestration/requirements-airflow.txt /tmp/orchestration/requirements-airflow.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt -r /tmp/orchestration/requirements-airflow.txt
