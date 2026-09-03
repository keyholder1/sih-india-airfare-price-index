"""SerpApi (Google Flights engine) source adapter.

Unlike ``indigo_source.py`` (credential-gated, no live call implemented)
and ``yatra_source.py`` (browser automation, block risk unknown), this
adapter calls a genuinely public, documented, self-service third-party
API and was verified against a real live response during this project's
recon (DEL->BLR, 2026-09-10 -- real IndiGo/Air India/Air India Express/
Akasa Air fares in INR).

WHAT THIS SOURCE ACTUALLY IS
-----------------------------
SerpApi is a commercial company whose product is scraping Google's own
search result pages (including Google Flights) and reselling structured
access to that data via a documented API, under SerpApi's own terms of
service. Using it means being a paying/free-tier customer of a real
product -- categorically different from this project's IndiGo/Akasa/Air
India findings, where the acting party would have been us defeating an
airline's own authentication. Observations from this source are tagged
``source="serpapi_google_flights"`` specifically so nobody downstream
mistakes this for a direct airline feed -- it is Google's aggregated
view of fares, not any single airline's live inventory.

VERIFIED RESPONSE SCHEMA (2026-09-02 recon session)
-----------------------------------------------------
    {
      "search_parameters": {"currency": "INR", ...},
      "best_flights": [ {...itinerary...}, ... ],
      "other_flights": [ {...itinerary...}, ... ],
      "price_insights": {"price_history": [[unix_ts, price], ...], ...}
    }

Both ``best_flights`` and ``other_flights`` share the same itinerary
shape:
    {
      "flights": [
        {"departure_airport": {"id": "DEL", "time": "2026-09-10 12:20"},
         "arrival_airport": {"id": "BLR", "time": "..."},
         "airline": "IndiGo", "flight_number": "6E 850", ...},
        ... (more than one entry only for a connecting itinerary)
      ],
      "total_duration": 180,
      "price": 8724,          # price for the WHOLE itinerary, not per leg
      "type": "One way"
    }

IMPORTANT: ``price`` belongs to the itinerary as a whole. A connecting
itinerary (e.g. DEL->NAG->BLR, 2 entries in "flights") still has exactly
ONE price for both legs combined -- confirmed against a real captured
example. This adapter therefore maps one itinerary to one
RawFareObservation (not one observation per leg), with
``stops = len(flights) - 1``, and takes ``airline``/route/time fields
from the itinerary's first leg.

``price_insights.price_history`` (a real historical price time series
Google computes for the route) is NOT currently mapped into
observations -- it's a different shape (a route-level time series, not
individual fare quotes) and is flagged here as a potentially useful
secondary signal for the project's 30-day back-test requirement, for
whoever owns that comparison to evaluate separately.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Optional

import httpx

from .models import RawFareObservation, SourceCallResult
from .source import FareSource, SearchRequest

ENV_API_KEY = "SERPAPI_API_KEY"
SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
REQUEST_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class SerpApiCredentials:
    api_key: str


def load_credentials_from_env() -> Optional[SerpApiCredentials]:
    """Read the SerpApi key from the environment. Returns ``None`` if
    absent -- callers must treat that as "source unavailable," never as
    "use a placeholder." Never logs or returns the key value anywhere
    else in this module.
    """
    api_key = os.environ.get(ENV_API_KEY)
    if not api_key:
        return None
    return SerpApiCredentials(api_key=api_key)


class SerpApiSource(FareSource):
    """Real, working adapter for SerpApi's Google Flights engine.

    Construct with no arguments to read the key from the environment
    (the normal path); pass ``credentials`` explicitly only for tests.
    """

    name = "SerpApi (Google Flights)"

    def __init__(self, credentials: Optional[SerpApiCredentials] = None, client: Optional[httpx.Client] = None) -> None:
        self._credentials = credentials if credentials is not None else load_credentials_from_env()
        self._client = client  # injectable for tests; created per-call otherwise

    def search_fares(self, request: SearchRequest) -> SourceCallResult:
        if self._credentials is None:
            return SourceCallResult(
                status="SOURCE_UNAVAILABLE",
                observations=[],
                error_detail=f"SerpApi API key not configured (set {ENV_API_KEY}). See .env.example.",
            )

        params = {
            "engine": "google_flights",
            "hl": "en",
            "type": "2",  # one-way
            "departure_id": request.origin,
            "arrival_id": request.destination,
            "outbound_date": request.flight_date.isoformat(),
            "currency": "INR",
            "api_key": self._credentials.api_key,
        }

        try:
            client = self._client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
            response = client.get(SERPAPI_ENDPOINT, params=params)
        except httpx.TimeoutException:
            return SourceCallResult(status="TIMEOUT", observations=[], error_detail="SerpApi request timed out.")
        except httpx.HTTPError as exc:
            return SourceCallResult(status="HTTP_ERROR", observations=[], error_detail=f"SerpApi request failed: {exc}")
        finally:
            if self._client is None:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass

        if response.status_code != 200:
            return SourceCallResult(
                status="HTTP_ERROR",
                observations=[],
                error_detail=f"SerpApi returned HTTP {response.status_code}: {response.text[:300]}",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            return SourceCallResult(status="PARSE_ERROR", observations=[], error_detail=f"Could not parse SerpApi response as JSON: {exc}")

        return self._to_result(payload, request)

    def _to_result(self, payload, request: SearchRequest) -> SourceCallResult:
        if not isinstance(payload, dict):
            return SourceCallResult(
                status="MALFORMED_RESPONSE",
                observations=[],
                error_detail=f"Expected a JSON object, got: {type(payload).__name__}",
            )

        # SerpApi's own error convention: {"error": "..."} on failures
        # such as an invalid/exhausted key, invalid params, etc. Bucketed
        # as SOURCE_UNAVAILABLE rather than guessed apart further -- the
        # exact cause is preserved in error_detail either way.
        if "error" in payload:
            return SourceCallResult(
                status="SOURCE_UNAVAILABLE",
                observations=[],
                error_detail=f"SerpApi reported an error: {payload['error']}",
            )

        best = payload.get("best_flights", [])
        other = payload.get("other_flights", [])
        if not isinstance(best, list) or not isinstance(other, list):
            return SourceCallResult(
                status="MALFORMED_RESPONSE",
                observations=[],
                error_detail="Expected 'best_flights'/'other_flights' to be lists.",
            )

        itineraries = best + other
        if not itineraries:
            return SourceCallResult(status="EMPTY_RESULT", observations=[])

        observations = []
        for itinerary in itineraries:
            obs = self._itinerary_to_observation(itinerary, request)
            if obs is not None:
                observations.append(obs)

        if not observations:
            return SourceCallResult(
                status="PARSE_ERROR",
                observations=[],
                error_detail="Itineraries were present but none had the expected fields.",
            )

        return SourceCallResult(status="SUCCESS", observations=observations)

    @staticmethod
    def _itinerary_to_observation(itinerary, request: SearchRequest) -> Optional[RawFareObservation]:
        """One itinerary (possibly multiple flight legs) -> one
        observation. Returns None (never raises) for a malformed entry
        so one bad itinerary doesn't sink the whole response -- the
        caller reports PARSE_ERROR only if EVERY itinerary fails this.
        """
        try:
            legs = itinerary["flights"]
            if not isinstance(legs, list) or not legs:
                return None
            first_leg = legs[0]
            airline = first_leg["airline"]
            departure_time = first_leg["departure_airport"]["time"]  # "YYYY-MM-DD HH:MM"
            flight_date_str = departure_time.split(" ")[0]
            price = itinerary["price"]
            if airline is None or price is None:
                return None
            total_fare = float(price)
        except (KeyError, TypeError, ValueError, IndexError):
            return None

        booking_token = itinerary.get("booking_token")
        observation_id = (
            f"serpapi_{request.origin}_{request.destination}_{flight_date_str}_{booking_token}"
            if booking_token
            else f"serpapi_{request.origin}_{request.destination}_{flight_date_str}_{airline}_{total_fare}"
        )

        return RawFareObservation(
            observation_id=observation_id,
            airline=airline,
            origin=request.origin,
            destination=request.destination,
            flight_date=flight_date_str,
            booking_date=request.booking_date.isoformat(),
            total_fare=total_fare,
            currency="INR",
            source="serpapi_google_flights",
            stops=len(legs) - 1,
            duration=itinerary.get("total_duration"),
        )
