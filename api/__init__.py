"""REST API (Phase 9): read-only endpoints over the dbt marts.

Serves dim_series, fct_observations_latest, and fct_observations_point_in_time -- see
api/main.py for the routes, README.md's API section for how to run it, and DECISIONS.md's
Phase 9 entry for the design choices (direct DuckDB access, connection-per-request, why the
as-of endpoint re-derives the point-in-time ranking instead of calling the dbt view).
"""
