-- Phase 1 (bridge-pipeline rebuild): one-time Snowflake trial account setup.
--
-- Run this yourself in a Snowflake worksheet (as ACCOUNTADMIN, which the first user on a new
-- trial account is by default) after signing up at https://signup.snowflake.com/. Not run by
-- any automation — dbt only ever connects as BRIDGE_DBT_ROLE / BRIDGE_DBT_USER afterward, never
-- as ACCOUNTADMIN.
--
-- What this creates: an XS warehouse that auto-suspends after 60s idle (so the trial's credits
-- aren't burned by an idle warehouse), one database with RAW/STAGING/MARTS schemas, and a
-- dedicated role + service user scoped to just this database — dbt never uses your personal
-- login. See DECISIONS.md for the warehouse-sizing rationale.

use role accountadmin;

-- Warehouse: XS is the smallest size and more than enough for ~20 small dbt models against a
-- few thousand rows each. AUTO_SUSPEND=60 (seconds) + AUTO_RESUME means it costs credits only
-- while actively running a query, never while idle.
create warehouse if not exists bridge_wh
  warehouse_size = 'XSMALL'
  auto_suspend = 60
  auto_resume = true
  initially_suspended = true
  comment = 'bridge-pipeline dbt builds — XS, 60s auto-suspend, never left running';

create database if not exists bridge_db
  comment = 'bridge-pipeline: FRED/ALFRED macro data for CRE credit analysis';

create schema if not exists bridge_db.raw
  comment = 'landed as close to the FRED/ALFRED API response as possible — casting and cleaning happen in staging';
create schema if not exists bridge_db.staging
  comment = 'stg_ models: renamed, typed, one row per raw table, no business logic';
create schema if not exists bridge_db.marts
  comment = 'dim_/fct_/mart_ models: the dimensional model and its consumption-ready outputs';

-- Dedicated role for dbt, scoped to only what it needs on this database + warehouse.
create role if not exists bridge_dbt_role;

grant usage on warehouse bridge_wh to role bridge_dbt_role;

grant usage on database bridge_db to role bridge_dbt_role;
grant create schema on database bridge_db to role bridge_dbt_role;

grant all on schema bridge_db.raw to role bridge_dbt_role;
grant all on schema bridge_db.staging to role bridge_dbt_role;
grant all on schema bridge_db.marts to role bridge_dbt_role;

grant all on future tables in schema bridge_db.raw to role bridge_dbt_role;
grant all on future views in schema bridge_db.raw to role bridge_dbt_role;
grant all on future tables in schema bridge_db.staging to role bridge_dbt_role;
grant all on future views in schema bridge_db.staging to role bridge_dbt_role;
grant all on future tables in schema bridge_db.marts to role bridge_dbt_role;
grant all on future views in schema bridge_db.marts to role bridge_dbt_role;

-- Service user for dbt. CHANGE_ME_PASSWORD: pick a strong password yourself here — do not
-- paste it into chat with an assistant. This becomes SNOWFLAKE_PASSWORD in your local .env
-- (gitignored) and, later in Phase 6, a GitHub Actions secret for CI.
create user if not exists bridge_dbt_user
  password = 'CHANGE_ME_PASSWORD'
  default_role = bridge_dbt_role
  default_warehouse = bridge_wh
  default_namespace = 'bridge_db.staging'
  must_change_password = false
  comment = 'service account for dbt — not a personal login';

grant role bridge_dbt_role to user bridge_dbt_user;

-- Sanity check: confirm the warehouse's auto-suspend is actually 60s, not the default 600s.
show warehouses like 'bridge_wh';
-- "auto_suspend" column in the result should read 60.
