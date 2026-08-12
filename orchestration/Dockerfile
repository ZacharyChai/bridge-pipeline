# Extends the stock Airflow image with this project's own runtime deps (requests,
# psycopg, SQLAlchemy, snowflake-sqlalchemy) plus dbt, so DAG tasks can `import ingest`,
# `import config`, etc. directly and the snowflake_dbt_pipeline DAG can shell out to a
# `dbt` binary that's actually on PATH -- no separate dbt container to coordinate.
ARG AIRFLOW_IMAGE_NAME=apache/airflow:3.3.0
FROM ${AIRFLOW_IMAGE_NAME}

COPY requirements.txt /tmp/requirements.txt
COPY orchestration/requirements-airflow.txt /tmp/requirements-airflow.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt -r /tmp/requirements-airflow.txt
