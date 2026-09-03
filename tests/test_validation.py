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


# --- non-default fare_field ---------------------------------------------------


def test_invalid_non_default_fare_field_is_rejected_even_when_total_fare_is_valid():
    # total_fare (the always-required column) is perfectly valid here, but
    # base_fare -- the *configured* comparable fare -- is missing. Without
    # validating the configured fare_field, this row would silently pass
    # validation, be counted in observations_used, and then contribute
    # nothing (NaN, dropped) to the actual representative-fare calculation.
    df = to_df([make_observation(base_fare=None, total_fare=5000.0)])
    valid, rejected = validate_observations(df, fare_field="base_fare")
    assert len(valid) == 0
    assert rejected["rejection_reason"].iloc[0] == REASON_INVALID_FARE


def test_negative_non_default_fare_field_is_rejected():
    df = to_df([make_observation(base_fare=-100.0, total_fare=5000.0)])
    valid, rejected = validate_observations(df, fare_field="base_fare")
    assert len(valid) == 0
    assert rejected["rejection_reason"].iloc[0] == REASON_INVALID_FARE


def test_valid_non_default_fare_field_passes():
    df = to_df([make_observation(base_fare=4400.0, total_fare=5000.0)])
    valid, rejected = validate_observations(df, fare_field="base_fare")
    assert len(valid) == 1
    assert len(rejected) == 0


def test_default_fare_field_behaviour_is_unaffected():
    # total_fare-only validation (the default) must still work exactly as
    # before regardless of what's in base_fare.
    df = to_df([make_observation(base_fare=None, total_fare=5000.0)])
    valid, rejected = validate_observations(df)
    assert len(valid) == 1
    assert len(rejected) == 0
