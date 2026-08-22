"""Shared config for both DAGs: the on-failure callback, the daily schedule, and the
retry policy -- defined once here instead of copy-pasted into each DAG file, since a
retry-policy or schedule change to one pipeline with no mechanism forcing the same
change in the other is exactly how the two would silently drift.

The on-failure callback is one structured log line per task failure, not a bare
traceback. In a real deployment this is where a Slack/PagerDuty call would go instead
of a log line -- the shape (dag/task/run/exception as one JSON event) is what that
integration would forward as-is.
"""

from __future__ import annotations

import json
import logging

import pendulum

log = logging.getLogger("airflow.task")


def log_failure(context: dict) -> None:
    ti = context["task_instance"]
    event = {
        "event": "task_failed",
        "dag_id": ti.dag_id,
        "task_id": ti.task_id,
        "run_id": context.get("run_id"),
        "try_number": ti.try_number,
        "exception": repr(context.get("exception")),
    }
    log.error(json.dumps(event))


SCHEDULE = "30 6 * * *"

# DAG-level default_args: applies to every task. Deliberately does NOT include
# retries -- retries belong only on each DAG's one genuinely flaky task (the FRED API
# call), via RETRY_ARGS below on that task's own @task(...) decorator. Putting retries
# here would silently apply them to every task, including deterministic failures
# (a data-quality violation, a broken dbt model) that should fail fast, not retry.
DEFAULT_ARGS = {
    "on_failure_callback": log_failure,
}

RETRY_ARGS = {
    "retries": 3,
    "retry_delay": pendulum.duration(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": pendulum.duration(minutes=20),
}
