"""Pydantic response models for the API -- one per mart this service reads from."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class Series(BaseModel):
    """One row of dim_series."""

    series_id: str
    title: str
    frequency: str
    units: str
    seasonal_adjustment: str
    observation_start_date: dt.date
    observation_end_date: dt.date
    category: str


class Observation(BaseModel):
    """One row of fct_observations_latest or fct_observations_point_in_time, joined to
    dim_date for a real calendar date rather than the surrogate date_key."""

    series_id: str
    date: dt.date
    value: float | None
    realtime_start_date: dt.date
    realtime_end_date: dt.date
