"""Yatra source adapter — real browser automation via Playwright.

Unlike ``indigo_source.py`` (credential-gated, no live call implemented
yet), this adapter is a genuine attempt at a real live source, because
recon during this project found something meaningfully different about
Yatra's fare endpoint:

    GET https://flight.yatra.com/lowest-fare-service/dom2/get-fare
        ?origin=...&destination=...&from=DD-MM-YYYY&to=DD-MM-YYYY
        &tripType=O&airlines=all&_i=...&src=srp

This endpoint requires **no Authorization header and no API key** --
unlike Akasa's and Air India's fare APIs (both gated behind a bearer
token this project correctly refused to reverse-engineer). What it does
expect is a browser session that has already passed Akamai Bot Manager's
JS-based checks (visible as ``bm_*`` / ``ak_bmsc`` / ``_abck`` cookies in
the request).

THE LINE THIS ADAPTER DOES NOT CROSS
-------------------------------------
It would be trivial, and WRONG, to copy a real browser's captured cookie
string into this file or into an HTTP client and replay it. That is
impersonating a browser session using artifacts Akamai's bot-detection
generated specifically to verify a real one -- exactly the "bypass bot
detection" this project's rules forbid, regardless of how easy it would
be. This file contains no captured cookie values, no bearer tokens, and
never will.

WHAT THIS ADAPTER DOES INSTEAD
-------------------------------
It drives an actual Playwright-controlled Chromium browser to the real
site, lets Yatra's and Akamai's own JavaScript run exactly as it would
for any real visitor, and performs a genuine UI search (fill origin/
destination/date, click search). Any cookies that browser ends up
holding are ones Akamai's own scripts issued to *that specific browser
instance* through the normal challenge flow -- not appropriated from
anyone else's session. This is the same category of thing the official
problem statement anticipates when it says a scraper "must handle
JavaScript-rendered pages ... session management."

HONEST ABOUT THE LIKELY OUTCOME
---------------------------------
Akamai Bot Manager is specifically designed to also detect automated
browsers (headless Chromium fingerprints, missing mouse/keyboard entropy,
etc.), independent of whether cookies are being replayed. It is entirely
possible -- arguably likely -- that this adapter gets blocked or served
a challenge page even though it never bypasses anything. If that happens,
the correct outcome is exactly what this code does: report
SOURCE_UNAVAILABLE / CAPTCHA_REQUIRED honestly, once, and stop. No
retry-with-a-different-fingerprint, no stealth plugins, no evasion
tuning. A block here is real evidence for the project's findings, not a
bug to engineer around.

REQUIREMENTS TO RUN THIS ADAPTER
-----------------------------------
    pip install playwright
    playwright install chromium

This adapter is NOT exercised by the deterministic test suite beyond
mocked/monkeypatched unit tests (see tests/test_scraper_yatra_source.py)
-- an actual live run against yatra.com is a manual/integration check
you run yourself, the same way the project brief asks for live scraping
to be an optional integration test only, never part of CI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .models import RawFareObservation, SourceCallResult
from .source import FareSource, SearchRequest

FARE_ENDPOINT_PATTERN = re.compile(r"/lowest-fare-service/dom2/get-fare")

#: Selectors are best-effort and WILL need adjusting if Yatra changes
#: their markup -- that is an ordinary, expected maintenance cost of any
#: UI-driven adapter, not a sign something is wrong with the approach.
#: Keeping them as named constants here (rather than buried inline)
#: makes that maintenance a one-line-per-field fix.
SEL_ORIGIN_INPUT = "#FromSector_show"
SEL_DESTINATION_INPUT = "#ToSector_show"
SEL_SEARCH_BUTTON = "#BtnSearch"
#: Verified via live DOM inspection (2026-09-02 recon session) -- MUI
#: auto-generated css-xxxx classes are unstable and NOT used here on
#: purpose; aria-label is a far more durable selector for this widget.
SEL_DEPARTURE_DATE_BUTTON = '[aria-label="Departure Date inputbox"]'
#: react-datepicker's own default "next month" arrow class -- library
#: default, not a site-specific custom class, so more likely to be
#: stable than most selectors here, but this specific one was NOT
#: independently confirmed during recon (only day cells and the trigger
#: button were). Verify before relying on it for horizons that cross a
#: month boundary (T+30, T+45).
SEL_CALENDAR_NEXT_MONTH = ".react-datepicker__navigation--next"
_MAX_MONTH_CLICKS = 3  # generous bound for T+45's worst case
# The site renders one autocomplete result list for both from/to fields;
# selecting by visible text avoids depending on a specific DOM id here.

_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _ordinal_suffix(day: int) -> str:
    if 10 <= day % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def _departure_day_aria_label(d: date) -> str:
    """Build the exact aria-label react-datepicker uses for one day cell,
    e.g. ``"Choose Tuesday, September 15th, 2026"`` -- verified against a
    real captured day cell during recon (see _perform_search_ui). Names
    are hardcoded in English rather than using strftime's locale-
    dependent %A/%B, since this must produce the same string regardless
    of the machine's OS locale settings.
    """
    weekday = _WEEKDAY_NAMES[d.weekday()]
    month = _MONTH_NAMES[d.month - 1]
    return f"Choose {weekday}, {month} {d.day}{_ordinal_suffix(d.day)}, {d.year}"


@dataclass(frozen=True)
class YatraFareEntry:
    """One parsed row from the get-fare response, before becoming a
    RawFareObservation. Kept as an explicit intermediate type so the
    "what does the raw API actually give us" step is separated from
    "how do we map that into our contract" -- makes it obvious which
    part to fix if Yatra changes their response shape."""

    airline: str
    total_fare: float
    flight_number: Optional[str] = None


class YatraSource(FareSource):
    """Real browser-automation adapter for Yatra's domestic fare-search
    endpoint. See module docstring for the ethical boundary this adapter
    stays inside, and for why a block is a legitimate possible outcome.
    """

    name = "Yatra"

    #: How long to wait for the get-fare network response after
    #: triggering a search, in milliseconds. Generous on purpose --
    #: this is a real page load with real JS execution, not an API call.
    RESPONSE_TIMEOUT_MS = 30_000

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless

    def search_fares(self, request: SearchRequest) -> SourceCallResult:
        try:
            from playwright.sync_api import (  # local import: optional heavy dep
                TimeoutError as PlaywrightTimeoutError,
                sync_playwright,
            )
        except ImportError:
            return SourceCallResult(
                status="SOURCE_UNAVAILABLE",
                observations=[],
                error_detail=(
                    "playwright is not installed. Run `pip install playwright && "
                    "playwright install chromium` to enable the Yatra adapter."
                ),
            )

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self._headless)
                try:
                    context = browser.new_context(
                        locale="en-IN",
                        timezone_id="Asia/Kolkata",
                    )
                    page = context.new_page()

                    fare_response_holder: dict = {}

                    def _capture_fare_response(response) -> None:
                        if FARE_ENDPOINT_PATTERN.search(response.url) and response.status == 200:
                            fare_response_holder["response"] = response

                    page.on("response", _capture_fare_response)

                    # Real navigation -- lets Yatra's + Akamai's own JS run
                    # for this genuine (if automated) browser instance.
                    page.goto("https://www.yatra.com/", timeout=self.RESPONSE_TIMEOUT_MS)

                    if self._looks_blocked(page):
                        return SourceCallResult(
                            status="SOURCE_UNAVAILABLE",
                            observations=[],
                            error_detail=(
                                "Yatra homepage returned a bot-check / CAPTCHA page "
                                "instead of the normal site. Not bypassed -- reported "
                                "as unavailable per project rules."
                            ),
                        )

                    self._perform_search_ui(page, request)

                    try:
                        page.wait_for_event(
                            "response",
                            predicate=lambda r: FARE_ENDPOINT_PATTERN.search(r.url) is not None,
                            timeout=self.RESPONSE_TIMEOUT_MS,
                        )
                    except PlaywrightTimeoutError:
                        if self._looks_blocked(page):
                            return SourceCallResult(
                                status="SOURCE_UNAVAILABLE",
                                observations=[],
                                error_detail="Blocked/CAPTCHA page shown during search; no fare response captured.",
                            )
                        return SourceCallResult(
                            status="TIMEOUT",
                            observations=[],
                            error_detail=f"No get-fare response observed within {self.RESPONSE_TIMEOUT_MS}ms.",
                        )

                    response = fare_response_holder.get("response")
                    if response is None:
                        return SourceCallResult(
                            status="TIMEOUT",
                            observations=[],
                            error_detail="Fare response event fired but was not captured.",
                        )

                    try:
                        payload = response.json()
                    except Exception as exc:  # noqa: BLE001 - genuinely any parse failure
                        return SourceCallResult(
                            status="PARSE_ERROR",
                            observations=[],
                            error_detail=f"Could not parse get-fare response as JSON: {exc}",
                        )

                    return self._to_result(payload, request)
                finally:
                    browser.close()
        except Exception as exc:  # noqa: BLE001 - Playwright/browser-level failures
            return SourceCallResult(
                status="SOURCE_UNAVAILABLE",
                observations=[],
                error_detail=f"Browser automation failed: {exc}",
            )

    def _perform_search_ui(self, page, request: SearchRequest) -> None:
        """Fill and submit the real search form. Left as a distinct
        method (rather than inlined) so it's the one place to update if
        Yatra changes their homepage's form markup -- see SEL_* constants.
        """
        page.click(SEL_ORIGIN_INPUT)
        page.fill(SEL_ORIGIN_INPUT, request.origin)
        page.click(f"text={request.origin}")

        page.click(SEL_DESTINATION_INPUT)
        page.fill(SEL_DESTINATION_INPUT, request.destination)
        page.click(f"text={request.destination}")

        # Verified via live DOM inspection: opens the react-datepicker
        # calendar widget.
        page.click(SEL_DEPARTURE_DATE_BUTTON)

        # Best-effort month navigation for horizons (T+30/T+45) that can
        # land in a later month than what's shown by default. Bounded
        # and swallows failures deliberately: if SEL_CALENDAR_NEXT_MONTH
        # is wrong or the target month is already visible, the
        # subsequent day-cell click either succeeds anyway or fails with
        # a clear timeout -- better than crashing this whole step on an
        # unverified navigation selector.
        today = date.today()
        months_ahead = (request.flight_date.year - today.year) * 12 + (request.flight_date.month - today.month)
        for _ in range(min(max(months_ahead, 0), _MAX_MONTH_CLICKS)):
            try:
                page.click(SEL_CALENDAR_NEXT_MONTH, timeout=2_000)
            except Exception:  # noqa: BLE001 - best-effort, see comment above
                break

        # Verified via live DOM inspection: react-datepicker day cells
        # use an aria-label of the exact form
        # "Choose Tuesday, September 15th, 2026" -- confirmed against a
        # real captured cell (id "react-datepicker__day--015" for that
        # date, whose displayed fare (Rs.8,671) matched the get-fare
        # response's "2026-09-15": {lf: 8671, ...} exactly, which also
        # independently confirms the response-schema decoding in
        # _to_result is correct).
        day_label = _departure_day_aria_label(request.flight_date)
        page.click(f'[aria-label="{day_label}"]')

    

    @staticmethod
    def _looks_blocked(page) -> bool:
        """Best-effort CAPTCHA/challenge-page detection. Deliberately
        conservative (checks for well-known Akamai/CAPTCHA markers) --
        false negatives here just mean a later step times out and is
        reported as TIMEOUT instead of SOURCE_UNAVAILABLE, which is a
        fine fallback; false positives would incorrectly stop a
        legitimate run.
        """
        try:
            title = page.title().lower()
        except Exception:  # noqa: BLE001
            return False
        blocked_markers = ("access denied", "are you a human", "captcha", "reference #")
        return any(marker in title for marker in blocked_markers)

    #: Real, verified response schema from recon (2026-09-02 session):
    #:   {"ld": "2026-10-27", "la": "QP", "lf": 7704, "isError": false,
    #:    "day": {"2026-09-02": {"lf": 8491, "la": "6E"}, ...}}
    #: "day" maps ISO date -> {lf: lowest fare that day, la: IATA airline
    #: code of that fare}. This is a LOWEST-FARE-PER-DAY CALENDAR, not a
    #: per-flight listing -- Yatra's backend has already picked the single
    #: cheapest fare for each date and discarded everything else (no
    #: flight number, no fare class, no fare spread). See module
    #: docstring "IMPORTANT LIMITATION" for what this means downstream.
    IATA_TO_AIRLINE_NAME = {
        "6E": "IndiGo",
        "AI": "Air India",
        "SG": "SpiceJet",
        "QP": "Akasa Air",
        "IX": "Air India Express",
        # "HR" appears in real responses but its carrier is not confirmed
        # -- deliberately NOT guessed here. Unmapped codes fall through to
        # the raw IATA string in _to_result rather than a fabricated name.
    }

    def _to_result(self, payload, request: SearchRequest) -> SourceCallResult:
        """Map Yatra's lowest-fare-calendar JSON into a RawFareObservation
        for the single date this request asked about.

        IMPORTANT LIMITATION (see module docstring): this endpoint only
        ever exposes the lowest fare per day, not individual flights.
        Every observation this method produces is tagged
        ``fare_type="LOWEST_OF_DAY"`` specifically so Data Quality / the
        Index Engine can distinguish it from sources that report every
        available fare -- treating the two as equivalent would silently
        bias any cross-source statistic (median, spread, etc.).
        """
        if not isinstance(payload, dict) or "day" not in payload:
            return SourceCallResult(
                status="MALFORMED_RESPONSE",
                observations=[],
                error_detail=f"Expected a dict with a 'day' key, got: {type(payload).__name__}",
            )

        day_map = payload["day"]
        if not isinstance(day_map, dict):
            return SourceCallResult(
                status="MALFORMED_RESPONSE",
                observations=[],
                error_detail=f"Expected 'day' to be a dict of date -> fare, got: {type(day_map).__name__}",
            )

        flight_date_key = request.flight_date.isoformat()
        entry = day_map.get(flight_date_key)

        if entry is None:
            # Date genuinely absent from the calendar Yatra returned --
            # different from EMPTY_RESULT-as-"no day map at all".
            return SourceCallResult(
                status="EMPTY_RESULT",
                observations=[],
                error_detail=f"No fare entry for {flight_date_key} in the returned calendar.",
            )

        if entry == {}:
            # Real responses can contain a genuinely empty {} for a date
            # (seen in recon, e.g. 2027-03-13) -- this means "no fare
            # available that day," not zero. Never fabricate a 0 fare.
            return SourceCallResult(status="EMPTY_RESULT", observations=[])

        try:
            fare_value = entry["lf"]
            iata_code = entry["la"]
            if fare_value is None or iata_code is None:
                raise KeyError("lf/la present but null")
            total_fare = float(fare_value)
        except (KeyError, TypeError, ValueError):
            return SourceCallResult(
                status="PARSE_ERROR",
                observations=[],
                error_detail=f"Day entry for {flight_date_key} did not have the expected 'lf'/'la' fields: {entry!r}",
            )

        airline_name = self.IATA_TO_AIRLINE_NAME.get(iata_code, iata_code)

        observation = RawFareObservation(
            observation_id=(
                f"yatra_{request.origin}_{request.destination}_"
                f"{flight_date_key}_{iata_code}_lowest"
            ),
            airline=airline_name,
            origin=request.origin,
            destination=request.destination,
            flight_date=flight_date_key,
            booking_date=request.booking_date.isoformat(),
            total_fare=total_fare,
            currency="INR",
            source="yatra",
            fare_type="LOWEST_OF_DAY",
        )
        return SourceCallResult(status="SUCCESS", observations=[observation])
