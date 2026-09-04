"""Tests for NaturalEvent.from_raw parsing -- especially the Point vs.
Polygon geometry rule (see eonet_models.py docstring): only Point
geometry (verified live to use standard GeoJSON [lon, lat] ordering) is
parsed; Polygon-only events (observed live for some flood events, with
unverified coordinate ordering) are excluded rather than risking a
silently wrong location."""

from datetime import datetime, timedelta

from index_engine.eonet_models import NaturalEvent

LABELS = {"wildfires": "Wildfire", "floods": "Flood"}


def _point_event(**overrides):
    base = {
        "id": "EONET_1",
        "title": "Wildfire in India 1028830",
        "categories": [{"id": "wildfires", "title": "Wildfires"}],
        "sources": [{"id": "SRC", "url": "https://example.com/src"}],
        "closed": None,
        "geometry": [{"date": "2026-05-31T19:00:00Z", "type": "Point", "coordinates": [82.674, 21.844]}],
    }
    base.update(overrides)
    return base


def test_point_geometry_parses_with_verified_lon_lat_order():
    event = NaturalEvent.from_raw(_point_event(), LABELS)
    assert event is not None
    assert event.longitude == 82.674
    assert event.latitude == 21.844
    assert event.category == "wildfires"
    assert event.category_label == "Wildfire"
    assert event.is_mock is False


def test_polygon_only_event_is_excluded_not_guessed():
    event = NaturalEvent.from_raw(
        _point_event(geometry=[{"date": "2026-06-22T20:00:00Z", "type": "Polygon", "coordinates": [[[28.23, 69.64], [28.24, 69.66]]]}]),
        LABELS,
    )
    assert event is None


def test_mixed_geometry_uses_the_point_entry():
    event = NaturalEvent.from_raw(
        _point_event(
            geometry=[
                {"date": "2026-06-20T00:00:00Z", "type": "Polygon", "coordinates": [[[1, 2], [3, 4]]]},
                {"date": "2026-06-22T20:00:00Z", "type": "Point", "coordinates": [72.9257, 19.1145]},
            ]
        ),
        LABELS,
    )
    assert event is not None
    assert event.longitude == 72.9257
    assert event.latitude == 19.1145


def test_missing_id_or_title_returns_none():
    assert NaturalEvent.from_raw({"title": "x", "categories": [], "geometry": []}, LABELS) is None
    assert NaturalEvent.from_raw({"id": "x", "categories": [], "geometry": []}, LABELS) is None


def test_missing_categories_returns_none():
    event = _point_event(categories=[])
    assert NaturalEvent.from_raw(event, LABELS) is None


def test_missing_geometry_returns_none():
    event = _point_event(geometry=[])
    assert NaturalEvent.from_raw(event, LABELS) is None


def test_source_url_falls_back_to_link_when_no_sources():
    event = _point_event(sources=[], link="https://eonet.gsfc.nasa.gov/api/v3/events/EONET_1")
    parsed = NaturalEvent.from_raw(event, LABELS)
    assert parsed.source_url == "https://eonet.gsfc.nasa.gov/api/v3/events/EONET_1"


def test_closed_field_maps_to_is_closed():
    open_event = NaturalEvent.from_raw(_point_event(closed=None), LABELS)
    closed_event = NaturalEvent.from_raw(_point_event(closed="2026-06-01T00:00:00Z"), LABELS)
    assert open_event.is_closed is False
    assert closed_event.is_closed is True


def test_unknown_category_falls_back_to_raw_id_as_label():
    event = _point_event(categories=[{"id": "manmade", "title": "Manmade"}])
    parsed = NaturalEvent.from_raw(event, {})  # no label configured for "manmade"
    assert parsed.category_label == "manmade"


def test_to_dict_serializes_event_date_as_iso_string():
    parsed = NaturalEvent.from_raw(_point_event(), LABELS)
    d = parsed.to_dict()
    assert d["event_date"] == "2026-05-31T19:00:00+00:00"
    assert isinstance(parsed.event_date, datetime)
    assert parsed.event_date.utcoffset() == timedelta(0)
