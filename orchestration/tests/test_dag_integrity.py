"""DAG-integrity checks: every DAG file must import cleanly and produce the task
structure, retries, and failure callback we expect.

Runs inside the Airflow container (`make dag-test`), not the project's own venv --
pip-installing Airflow itself into requirements-dev.txt alongside dbt-core risked real
dependency conflicts (both are large Apache projects with overlapping transitive pins)
for a test that only needs an environment where Airflow is already installed correctly.
"""

from __future__ import annotations

import sys

from airflow.models import DagBag

# Airflow's real DAG processor (the `airflow-dag-processor` service) puts the dags folder
# on sys.path itself before importing, which is why `from callbacks import log_failure`
# works there. A bare DagBag() call from a plain pytest process doesn't get that for free.
sys.path.insert(0, "/opt/airflow/dags")

EXPECTED_TASKS = {
    "legacy_postgres_pipeline": {"extract", "quality_gate", "load"},
    "snowflake_dbt_pipeline": {"ingest_series", "dbt_build"},
}


def _dagbag() -> DagBag:
    # No include_examples kwarg in Airflow 3's DagBag -- AIRFLOW__CORE__LOAD_EXAMPLES=false
    # (set in orchestration/docker-compose.yaml) is what actually keeps examples out.
    return DagBag(dag_folder="/opt/airflow/dags")


def test_no_import_errors():
    dagbag = _dagbag()
    assert dagbag.import_errors == {}, dagbag.import_errors


def test_expected_dags_present():
    dagbag = _dagbag()
    assert set(EXPECTED_TASKS) <= set(dagbag.dag_ids)


def test_expected_task_structure():
    dagbag = _dagbag()
    for dag_id, expected_tasks in EXPECTED_TASKS.items():
        dag = dagbag.get_dag(dag_id)
        assert dag is not None, f"{dag_id} failed to load"
        assert {t.task_id for t in dag.tasks} == expected_tasks


def test_dags_have_retries_and_failure_callback():
    dagbag = _dagbag()
    for dag_id in EXPECTED_TASKS:
        dag = dagbag.get_dag(dag_id)
        for t in dag.tasks:
            assert t.retries and t.retries >= 1, f"{dag_id}.{t.task_id} has no retries"
            assert t.on_failure_callback is not None, (
                f"{dag_id}.{t.task_id} has no on_failure_callback"
            )
