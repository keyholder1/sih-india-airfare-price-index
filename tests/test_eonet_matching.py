"""Tests for eonet_matching.py -- haversine distance, geographic
proximity scoring, temporal proximity scoring, and combined relevance
ranking. All inputs are real, verified coordinates (BLR/DEL from
index_engine.geo_metadata.CITY_COORDINATES, the same table
route_map_objects uses for the dashboard's India map)."""

from datetime import datetime, timedelta, timezone

import pytest

from index_engine.eonet_matching import (
    EonetMatchingConfig,
    haversine_km,
    rank_events,
    score_event,
)
from index_engine.eonet_models import NaturalEvent
from index_engine.geo_metadata import CITY_COORDINATES
from index_engine.news_models import RouteMovement


def _event(event_id="EONET_1", lat=28.6139, lon=77.2090, days_ago=0, category="severeStorms", is_closed=False):
    event_date = datetime(2026, 9, 4, tzinfo=timezone.utc) - timedelta(days=days_ago)
    return NaturalEvent(
        event_id=event_id,
        title="Test event",
        category=category,
        category_label=category,
        event_date=event_date,
        latitude=lat,
        longitude=lon,
        is_closed=is_closed,
        source_url="https://eonet.gsfc.nasa.gov/api/v3/events/" + event_id,
    )


def _movement(origin="BLR", destination="DEL", change_pct=10.0, as_of=None):
    return RouteMovement(
        route=f"{origin}-{destination}",
        origin=origin,
        destination=destination,
        change_pct=change_pct,
        metric="mom",
        period="2026-09",
        as_of=as_of or datetime(2026, 9, 4, tzinfo=timezone.utc),
    )


# --- haversine ---


def test_haversine_zero_for_identical_points():
    assert haversine_km(28.6139, 77.2090, 28.6139, 77.2090) == 0.0


def test_haversine_known_distance_del_to_blr_is_realistic():
    # Real great-circle distance DEL<->BLR is ~1740km.
    d = haversine_km(*CITY_COORDINATES["DEL"], *CITY_COORDINATES["BLR"])
    assert 1700 <= d <= 1800


# --- geographic scoring ---


def test_event_at_destination_coordinates_scores_max_geo_relevance():
    event = _event(lat=CITY_COORDINATES["DEL"][0], lon=CITY_COORDINATES["DEL"][1])
    match = score_event(event, _movement())
    assert match is not None
    assert match.distance_from_destination_km < 1.0
    assert "destination" in match.relevance_reason[0]


def test_event_far_outside_radius_scores_zero_geo_component():
    # A point far from India (roughly Europe) -- outside any reasonable radius.
    event = _event(lat=48.8566, lon=2.3522, days_ago=0)  # Paris, same day as the movement
    match = score_event(event, _movement(), EonetMatchingConfig(radius_km=300))
    # Geo component must be fully excluded even though the date lines up
    # exactly -- no "within Nkm of ..." reason should appear.
    assert not any("km of" in r for r in match.relevance_reason)


def test_event_far_away_and_long_ago_is_excluded_by_rank():
    event = _event(lat=48.8566, lon=2.3522, days_ago=60)  # Paris, 60 days ago
    match = score_event(event, _movement(), EonetMatchingConfig(radius_km=300, time_window_days=14))
    assert match.relevance_score < 0.35  # would be filtered by rank_events' min_relevance


def test_route_with_no_known_coordinates_returns_none():
    movement = _movement(origin="ZZZ", destination="YYY")
    event = _event()
    assert score_event(event, movement) is None


def test_closer_of_origin_or_destination_is_used():
    # Event near BLR (origin), far from DEL (destination).
    event = _event(lat=CITY_COORDINATES["BLR"][0] + 0.1, lon=CITY_COORDINATES["BLR"][1] + 0.1)
    match = score_event(event, _movement())
    assert match.distance_from_origin_km < match.distance_from_destination_km
    assert "origin" in match.relevance_reason[0]


# --- temporal scoring ---


def test_event_on_same_day_as_movement_scores_max_temporal_relevance():
    event = _event(lat=CITY_COORDINATES["DEL"][0], lon=CITY_COORDINATES["DEL"][1], days_ago=0)
    match = score_event(event, _movement())
    assert match.temporal_distance_days == 0.0


def test_event_outside_time_window_scores_zero_temporal_component():
    event = _event(lat=CITY_COORDINATES["DEL"][0], lon=CITY_COORDINATES["DEL"][1], days_ago=30)
    config = EonetMatchingConfig(time_window_days=14)
    match = score_event(event, _movement(), config)
    # Geo score still contributes (event is at DEL exactly), but no
    # "within Nd of the movement date" reason should be present.
    assert not any("movement date" in r for r in match.relevance_reason)


def test_event_within_window_has_partial_decayed_score():
    near = score_event(
        _event(lat=CITY_COORDINATES["DEL"][0], lon=CITY_COORDINATES["DEL"][1], days_ago=1), _movement()
    )
    far = score_event(
        _event(lat=CITY_COORDINATES["DEL"][0], lon=CITY_COORDINATES["DEL"][1], days_ago=10), _movement()
    )
    assert near.relevance_score > far.relevance_score


# --- config validation ---


def test_invalid_radius_raises():
    with pytest.raises(ValueError):
        EonetMatchingConfig(radius_km=0)


def test_invalid_time_window_raises():
    with pytest.raises(ValueError):
        EonetMatchingConfig(time_window_days=-1)


def test_invalid_min_relevance_raises():
    with pytest.raises(ValueError):
        EonetMatchingConfig(min_relevance=1.5)


# --- ranking ---


def test_rank_events_orders_by_relevance_descending():
    close = _event(event_id="EONET_close", lat=CITY_COORDINATES["DEL"][0], lon=CITY_COORDINATES["DEL"][1], days_ago=0)
    far = _event(event_id="EONET_far", lat=CITY_COORDINATES["DEL"][0] + 2, lon=CITY_COORDINATES["DEL"][1] + 2, days_ago=10)
    ranked = rank_events([far, close], _movement())
    assert ranked[0].event.event_id == "EONET_close"


def test_rank_events_deduplicates_by_event_id():
    event = _event(event_id="EONET_dup", lat=CITY_COORDINATES["DEL"][0], lon=CITY_COORDINATES["DEL"][1])
    duplicate = _event(event_id="EONET_dup", lat=CITY_COORDINATES["DEL"][0], lon=CITY_COORDINATES["DEL"][1])
    ranked = rank_events([event, duplicate], _movement())
    assert len(ranked) == 1


def test_rank_events_respects_top_n():
    events = [_event(event_id=f"EONET_{i}", lat=CITY_COORDINATES["DEL"][0], lon=CITY_COORDINATES["DEL"][1]) for i in range(10)]
    ranked = rank_events(events, _movement(), EonetMatchingConfig(top_n=3))
    assert len(ranked) == 3


def test_rank_events_filters_below_min_relevance():
    irrelevant = _event(lat=48.8566, lon=2.3522, days_ago=60)  # Paris, 60 days ago
    ranked = rank_events([irrelevant], _movement())
    assert ranked == []
