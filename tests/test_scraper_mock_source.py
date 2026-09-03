from datetime import date

from scraper.mock_source import MockFareSource, default_mock_sources
from scraper.source import SearchRequest


def _request(origin="BLR", destination="DEL", flight_date=date(2026, 9, 15), booking_date=date(2026, 9, 1)):
    return SearchRequest(origin=origin, destination=destination, flight_date=flight_date, booking_date=booking_date)


def test_mock_source_is_always_labelled_as_mock():
    source = MockFareSource("MockTest", "TestAir", 4000.0, 500.0)
    result = source.search_fares(_request())
    assert result.status == "SUCCESS"
    assert result.observations[0].is_mock is True


def test_mock_source_currency_is_inr_and_fare_is_positive():
    source = MockFareSource("MockTest", "TestAir", 4000.0, 500.0)
    obs = source.search_fares(_request()).observations[0]
    assert obs.currency == "INR"
    assert obs.total_fare > 0


def test_mock_source_is_deterministic_same_inputs_same_output():
    source = MockFareSource("MockTest", "TestAir", 4000.0, 500.0)
    first = source.search_fares(_request()).observations[0]
    second = source.search_fares(_request()).observations[0]
    assert first.total_fare == second.total_fare
    assert first.observation_id == second.observation_id


def test_mock_source_different_dates_produce_different_observation_ids():
    source = MockFareSource("MockTest", "TestAir", 4000.0, 500.0)
    a = source.search_fares(_request(flight_date=date(2026, 9, 15))).observations[0]
    b = source.search_fares(_request(flight_date=date(2026, 10, 1))).observations[0]
    assert a.observation_id != b.observation_id


def test_multiple_mock_sources_do_not_collide_on_observation_id():
    sources = default_mock_sources()
    ids = {s.search_fares(_request()).observations[0].observation_id for s in sources}
    assert len(ids) == len(sources)  # every source's id is distinct for the same route/date


def test_multi_source_collection_returns_distinct_fares_not_averaged():
    """Item 6 of the brief: BLR->DEL should show each source's own quote,
    never a single averaged number."""
    sources = default_mock_sources()
    fares = [s.search_fares(_request()).observations[0].total_fare for s in sources]
    assert len(fares) == 3
    assert len(set(fares)) > 1  # sources deliberately have different fare distributions


def test_mock_source_configured_empty_result_route_returns_empty_status():
    source = MockFareSource("MockTest", "TestAir", 4000.0, 500.0, empty_result_routes=frozenset({"BLR-DEL"}))
    result = source.search_fares(_request(origin="BLR", destination="DEL"))
    assert result.status == "EMPTY_RESULT"
    assert result.observations == []


def test_optional_fields_are_populated_not_null_when_mock_source_provides_them():
    source = MockFareSource("MockTest", "TestAir", 4000.0, 500.0)
    obs = source.search_fares(_request()).observations[0]
    assert obs.fare_class is not None
    assert obs.base_fare is not None
    assert obs.stops is not None


def test_source_url_is_null_for_mock_data_not_fabricated():
    # The mock generator has no real page it scraped — it must not invent one.
    source = MockFareSource("MockTest", "TestAir", 4000.0, 500.0)
    obs = source.search_fares(_request()).observations[0]
    assert obs.source_url is None
