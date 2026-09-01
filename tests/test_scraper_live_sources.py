"""Live-source adapter behaviour — deliberately does not depend on any
live airline/OTA website (item 24 of the brief): every one of these
sources is documented as SOURCE_UNAVAILABLE today, and this test suite
proves that adapter behaviour deterministically, with no network I/O."""

from datetime import date

from scraper.live_sources import EVALUATED_SOURCES, LIVE_SOURCES, UnavailableLiveSource
from scraper.source import SearchRequest


def _request():
    return SearchRequest(origin="BLR", destination="DEL", flight_date=date(2026, 9, 15), booking_date=date(2026, 9, 1))


def test_evaluated_sources_list_is_non_empty_and_documented():
    assert len(EVALUATED_SOURCES) >= 3
    for profile in EVALUATED_SOURCES:
        assert profile.domain
        assert profile.reason_unavailable
        assert profile.access_method in ("OFFICIAL_AIRLINE_WEBSITE", "OTA_WEBSITE", "THIRD_PARTY_API")


def test_every_evaluated_source_is_currently_marked_unavailable():
    # As of this writing, no source can be legitimately live-scraped
    # without credentials nobody has provided — see docs/scraper.md.
    for profile in EVALUATED_SOURCES:
        source = UnavailableLiveSource(profile)
        result = source.search_fares(_request())
        assert result.status == "SOURCE_UNAVAILABLE"
        assert result.observations == []
        assert result.error_detail  # always has a documented reason, never a bare failure


def test_unavailable_source_never_raises():
    for profile in EVALUATED_SOURCES:
        source = UnavailableLiveSource(profile)
        # Must not raise for any well-formed request — a structured failure,
        # not a crash.
        source.search_fares(_request())


def test_live_sources_registry_matches_evaluated_sources_count():
    assert len(LIVE_SOURCES) == len(EVALUATED_SOURCES)


def test_sources_requiring_credentials_are_flagged_as_such():
    # IndiGo: a real developer/NDC API exists, just not yet approved/credentialed
    # for this project (updated finding — see docs/scraper.md).
    indigo = next(p for p in EVALUATED_SOURCES if p.name == "IndiGo")
    assert indigo.requires_credentials is True
    assert indigo.api_exists is True


def test_amadeus_self_service_portal_shutdown_is_reflected_accurately():
    # UPDATED FINDING: the Amadeus self-service portal previously assumed
    # available has since shut down — api_exists must not still claim a
    # working self-service API exists (see docs/scraper.md).
    amadeus = next(p for p in EVALUATED_SOURCES if "Amadeus" in p.name)
    assert amadeus.api_exists is False
    assert "shut down" in amadeus.limitations.lower()


def test_aviationstack_documented_as_wrong_data_type_not_just_missing_key():
    aviationstack = next(p for p in EVALUATED_SOURCES if "viationstack" in p.name)
    assert "fare" in aviationstack.limitations.lower() or "price" in aviationstack.limitations.lower()
