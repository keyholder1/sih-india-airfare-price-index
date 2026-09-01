"""Proves scraper output conforms to docs/data_contract.md: required
fields present with valid types, positive fares, INR currency, valid
origin/destination, stable observation IDs, source metadata present, and
optional fields left null (never fabricated) when a source doesn't supply
them."""

from datetime import date

from index_engine.config import REQUIRED_COLUMNS
from scraper.mock_source import MockFareSource
from scraper.models import RawFareObservation, SourceCallResult
from scraper.source import FareSource, SearchRequest


def test_required_columns_from_data_contract_are_all_fields_on_raw_observation():
    record = RawFareObservation(
        observation_id="X", airline="Y", origin="AAA", destination="BBB",
        flight_date="2026-09-15", booking_date="2026-09-01", total_fare=100.0, currency="INR",
    ).to_record()
    for column in REQUIRED_COLUMNS:
        assert column in record, f"missing required contract field {column}"


def test_mock_source_output_has_required_fields_valid_dates_and_positive_fare():
    source = MockFareSource("MockTest", "TestAir", 4000.0, 500.0)
    request = SearchRequest(origin="BLR", destination="DEL", flight_date=date(2026, 9, 15), booking_date=date(2026, 9, 1))
    record = source.search_fares(request).observations[0].to_record()

    for column in REQUIRED_COLUMNS:
        assert record[column] not in (None, ""), f"{column} must not be null/blank"
    date.fromisoformat(record["flight_date"])
    date.fromisoformat(record["booking_date"])
    assert record["total_fare"] > 0
    assert record["currency"] == "INR"
    assert record["origin"] != record["destination"]
    assert len(record["origin"]) == 3 and record["origin"].isupper()
    assert len(record["destination"]) == 3 and record["destination"].isupper()


def test_observation_id_is_stable_across_repeated_calls():
    source = MockFareSource("MockTest", "TestAir", 4000.0, 500.0)
    request = SearchRequest(origin="BLR", destination="DEL", flight_date=date(2026, 9, 15), booking_date=date(2026, 9, 1))
    id_a = source.search_fares(request).observations[0].observation_id
    id_b = source.search_fares(request).observations[0].observation_id
    assert id_a == id_b


def test_source_metadata_present_on_every_observation():
    source = MockFareSource("MockTest", "TestAir", 4000.0, 500.0)
    request = SearchRequest(origin="BLR", destination="DEL", flight_date=date(2026, 9, 15), booking_date=date(2026, 9, 1))
    record = source.search_fares(request).observations[0].to_record()
    assert record["source"] == "MockTest"


class _PartialSource(FareSource):
    """A source that only ever supplies the required fields — proves the
    scraper leaves genuinely-unavailable optional fields null rather than
    inventing plausible-looking values (item 2 of the brief)."""

    name = "PartialTest"

    def search_fares(self, request: SearchRequest) -> SourceCallResult:
        obs = RawFareObservation(
            observation_id=f"OBS_PARTIAL_{request.origin}_{request.destination}",
            airline="TestAir",
            origin=request.origin,
            destination=request.destination,
            flight_date=request.flight_date.isoformat(),
            booking_date=request.booking_date.isoformat(),
            total_fare=5000.0,
            currency="INR",
        )
        return SourceCallResult(status="SUCCESS", observations=[obs])


def test_optional_fields_default_to_null_not_fabricated_when_source_lacks_them():
    source = _PartialSource()
    request = SearchRequest(origin="BLR", destination="DEL", flight_date=date(2026, 9, 15), booking_date=date(2026, 9, 1))
    record = source.search_fares(request).observations[0].to_record()
    for optional_field in ("fare_class", "fare_type", "base_fare", "taxes", "fees", "stops", "duration", "baggage", "availability"):
        assert record[optional_field] is None
