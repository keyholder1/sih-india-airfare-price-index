"""A deterministic, clearly-labelled fake :class:`~scraper.source.FareSource`
for development, tests, and the SIH demo.

Every observation this produces has ``is_mock=True`` and a ``source`` name
prefixed ``Mock`` — see ``docs/scraper.md`` "Mock vs live" for why that
prefix is load-bearing (the integration demo refuses to describe anything
carrying it as real data). Fares are a deterministic function of
(source, route, flight_date, booking_date) — same inputs always produce
the same fare, so demos and tests are reproducible without a fixed global
random seed leaking between calls (see docs/scraper.md "Reproducibility").

This is not a statistical model of real airfares. It exists only so the
scraper -> Data Quality -> Index Engine pipeline has something to run
against before a real, permitted source is connected.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import List

from .models import RawFareObservation, SourceCallResult
from .source import FareSource, SearchRequest

_FARE_CLASSES = ("Economy", "PremiumEconomy")
_FARE_TYPES = ("Refundable", "NonRefundable")


def _deterministic_unit(*parts: str) -> float:
    """A stable float in [0, 1) derived from ``parts`` — same inputs
    always produce the same output, independent of any global random
    state (unlike ``random.seed(...)``, which every caller in the process
    shares and can accidentally perturb)."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _deterministic_observation_id(source: str, origin: str, destination: str, flight_date: str, booking_date: str, salt: str) -> str:
    digest = hashlib.sha1(f"{source}|{origin}|{destination}|{flight_date}|{booking_date}|{salt}".encode("utf-8")).hexdigest()
    return f"OBS_MOCK_{digest[:16]}"


class MockFareSource(FareSource):
    """One simulated airline/OTA. Instantiate several (see
    :func:`default_mock_sources`) to simulate the multi-source collection
    the project brief describes (item 6): the same route/date quoted
    differently by IndiGo, Air India, and an OTA reseller.
    """

    def __init__(
        self,
        source_name: str,
        airline: str,
        base_fare_mean: float,
        base_fare_spread: float,
        empty_result_routes: frozenset = frozenset(),
    ) -> None:
        self.name = source_name
        self.airline = airline
        self.base_fare_mean = base_fare_mean
        self.base_fare_spread = base_fare_spread
        #: Routes this mock source deliberately returns nothing for, so
        #: EMPTY_RESULT handling has something real to exercise in tests/
        #: demos rather than only ever seeing SUCCESS.
        self.empty_result_routes = empty_result_routes

    def search_fares(self, request: SearchRequest) -> SourceCallResult:
        route = f"{request.origin}-{request.destination}"
        flight_date = request.flight_date.isoformat()
        booking_date = request.booking_date.isoformat()

        if route in self.empty_result_routes:
            return SourceCallResult(status="EMPTY_RESULT", observations=[])

        unit = _deterministic_unit(self.name, route, flight_date, booking_date)
        fare_class = _FARE_CLASSES[int(unit * 1000) % len(_FARE_CLASSES)]
        fare_type = _FARE_TYPES[int(unit * 10000) % len(_FARE_TYPES)]

        base_fare = round(self.base_fare_mean + (unit * 2 - 1) * self.base_fare_spread, 2)
        base_fare = max(base_fare, 500.0)
        taxes = round(base_fare * 0.12, 2)
        fees = round(base_fare * 0.02, 2)
        total_fare = round(base_fare + taxes + fees, 2)

        stops = 0 if unit < 0.85 else 1
        duration_hours = round(1.5 + (request.origin != request.destination) * unit * 3, 2)
        now = datetime.now(timezone.utc).isoformat()

        observation = RawFareObservation(
            observation_id=_deterministic_observation_id(self.name, request.origin, request.destination, flight_date, booking_date, fare_class),
            airline=self.airline,
            origin=request.origin,
            destination=request.destination,
            flight_date=flight_date,
            booking_date=booking_date,
            total_fare=total_fare,
            currency="INR",
            timestamp=now,
            source=self.name,
            fare_class=fare_class,
            fare_type=fare_type,
            base_fare=base_fare,
            taxes=taxes,
            fees=fees,
            stops=stops,
            duration=duration_hours,
            baggage="15kg" if fare_class == "Economy" else "25kg",
            availability=True,
            source_url=None,
            is_mock=True,
        )
        return SourceCallResult(status="SUCCESS", observations=[observation])


def default_mock_sources(empty_result_routes: frozenset = frozenset()) -> List[MockFareSource]:
    """Three simulated sources per route/date — matches the BLR->DEL
    example in the project brief (IndiGo / Air India / an OTA), each with
    a different fare distribution so they don't coincidentally agree."""
    return [
        MockFareSource("MockIndiGo", "IndiGo", base_fare_mean=4200.0, base_fare_spread=900.0, empty_result_routes=empty_result_routes),
        MockFareSource("MockAirIndia", "Air India", base_fare_mean=4800.0, base_fare_spread=1200.0, empty_result_routes=empty_result_routes),
        MockFareSource("MockOTA_ClearSky", "IndiGo", base_fare_mean=4450.0, base_fare_spread=1000.0, empty_result_routes=empty_result_routes),
    ]
