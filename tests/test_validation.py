import pandas as pd

from conftest import make_observation, to_df
from index_engine.validation import (
    REASON_IMPOSSIBLE_BOOKING_HORIZON,
    REASON_INVALID_DATE,
    REASON_INVALID_FARE,
    REASON_MISSING_REQUIRED_FIELD,
    REASON_SAME_ORIGIN_DESTINATION,
    validate_observations,
)


def test_valid_observation_passes():
    df = to_df([make_observation()])
    valid, rejected = validate_observations(df)
    assert len(valid) == 1
    assert len(rejected) == 0


def test_zero_or_negative_fare_is_rejected():
    df = to_df([make_observation(total_fare=0), make_observation(total_fare=-500)])
    valid, rejected = validate_observations(df)
    assert len(valid) == 0
    assert (rejected["rejection_reason"] == REASON_INVALID_FARE).all()


def test_missing_required_field_is_rejected():
    df = to_df([make_observation(airline="")])
    _, rejected = validate_observations(df)
    assert rejected["rejection_reason"].iloc[0] == REASON_MISSING_REQUIRED_FIELD


def test_unparseable_date_is_rejected():
    df = to_df([make_observation(flight_date="not-a-date")])
    _, rejected = validate_observations(df)
    assert rejected["rejection_reason"].iloc[0] == REASON_INVALID_DATE


def test_same_origin_and_destination_is_rejected():
    df = to_df([make_observation(origin="DEL", destination="DEL")])
    _, rejected = validate_observations(df)
    assert rejected["rejection_reason"].iloc[0] == REASON_SAME_ORIGIN_DESTINATION


def test_booking_after_flight_is_rejected():
    df = to_df([make_observation(flight_date="2026-01-01", booking_date="2026-02-01")])
    _, rejected = validate_observations(df)
    assert rejected["rejection_reason"].iloc[0] == REASON_IMPOSSIBLE_BOOKING_HORIZON
