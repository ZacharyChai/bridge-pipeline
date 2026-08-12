"""Shared on-failure callback for both DAGs: one structured log line per task failure,
not a bare traceback. In a real deployment this is where a Slack/PagerDuty call would go
instead of a log line -- the shape (dag/task/run/exception as one JSON event) is what
that integration would forward as-is.
"""

from __future__ import annotations

import json
import logging

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
