"""Evaluated real-world fare sources.

Every entry below was checked against the constraints this project
operates under: no bypassing bot protection/CAPTCHAs/auth, respect
robots.txt and each site's Terms of Service, and no credentials beyond
what the project owner has explicitly configured (none, at the time this
was written). See docs/scraper.md "Source evaluation" for the full
write-up including what was empirically tested this session versus what
is documented from general knowledge of these companies' published terms.

As of this writing, **every** entry is ``SOURCE_UNAVAILABLE`` — not
because the architecture can't support a live source, but because no
source this project has looked at can be accessed both legitimately and
without credentials nobody has provided. ``UnavailableLiveSource`` makes
that failure explicit and structured (see ``models.SourceCallResult``)
rather than silently returning nothing or, worse, fabricating a fare.

To add a real, permitted source once one exists (an official partner API
with issued credentials, for example): add a ``SourceProfile`` here for
documentation, then implement a new ``FareSource`` subclass that actually
calls it — nothing else in this package changes, the same way
``NewsProvider`` in ``index_engine.news_provider`` is designed to be
extended later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal

from .models import SourceCallResult
from .source import FareSource, SearchRequest

AccessMethod = Literal["OFFICIAL_AIRLINE_WEBSITE", "OTA_WEBSITE", "THIRD_PARTY_API"]
RobotsTxtStatus = Literal["ALLOWS", "DISALLOWS_RELEVANT_PATHS", "FETCH_BLOCKED_OR_TIMED_OUT", "NOT_INDEPENDENTLY_CHECKED"]


@dataclass(frozen=True)
class SourceProfile:
    """Documentation-as-data for one evaluated source — this is what item
    4 of the project brief asks each source to record."""

    name: str
    domain: str
    access_method: AccessMethod
    robots_txt_status: RobotsTxtStatus
    api_exists: bool
    requires_credentials: bool
    rate_limits_known: str
    fields_available: str
    limitations: str
    reason_unavailable: str
    empirically_tested_this_session: bool


#: Representative, not exhaustive — see docs/scraper.md for the rationale
#: on why a representative sample is the right amount of evaluation here.
EVALUATED_SOURCES: List[SourceProfile] = [
    SourceProfile(
        name="IndiGo",
        domain="www.goindigo.in",
        access_method="OFFICIAL_AIRLINE_WEBSITE",
        robots_txt_status="FETCH_BLOCKED_OR_TIMED_OUT",
        api_exists=False,
        requires_credentials=False,
        rate_limits_known="Unknown — request never completed",
        fields_available="Unknown — not reachable programmatically this session",
        limitations="No public fare-search API; only an interactive booking website.",
        reason_unavailable=(
            "An automated fetch of https://www.goindigo.in/robots.txt timed out during "
            "evaluation, consistent with bot-protection/CDN challenge behaviour rather than a "
            "plain static file. No public API exists. Search results/fares are only reachable "
            "through the interactive booking flow, which this project will not automate without "
            "confirming it's permitted and without bypassing any protection it has."
        ),
        empirically_tested_this_session=True,
    ),
    SourceProfile(
        name="Air India",
        domain="www.airindia.com",
        access_method="OFFICIAL_AIRLINE_WEBSITE",
        robots_txt_status="NOT_INDEPENDENTLY_CHECKED",
        api_exists=False,
        requires_credentials=False,
        rate_limits_known="Unknown",
        fields_available="Unknown",
        limitations="No public fare-search API; interactive booking website only.",
        reason_unavailable=(
            "Not independently fetched this session (time-boxed to a representative sample — "
            "see docs/scraper.md); same category as IndiGo (official airline site, no public "
            "fare API, standard airline ToS prohibiting automated data extraction). Treated as "
            "unavailable until someone actually re-checks it rather than assuming from category."
        ),
        empirically_tested_this_session=False,
    ),
    SourceProfile(
        name="MakeMyTrip",
        domain="www.makemytrip.com",
        access_method="OTA_WEBSITE",
        robots_txt_status="FETCH_BLOCKED_OR_TIMED_OUT",
        api_exists=False,
        requires_credentials=True,
        rate_limits_known="Unknown — request never completed",
        fields_available="Unknown — not reachable programmatically this session",
        limitations="Public affiliate/partner APIs exist for OTAs like this in general, but require a signed partner agreement and issued credentials this project does not have.",
        reason_unavailable=(
            "An automated fetch of https://www.makemytrip.com/robots.txt timed out during "
            "evaluation, consistent with bot-protection. MakeMyTrip's Terms of Use prohibit "
            "automated scraping/data-mining of the site (standard OTA ToS clause). Any partner "
            "API would require credentials nobody has configured for this project."
        ),
        empirically_tested_this_session=True,
    ),
    SourceProfile(
        name="Cleartrip",
        domain="www.cleartrip.com",
        access_method="OTA_WEBSITE",
        robots_txt_status="NOT_INDEPENDENTLY_CHECKED",
        api_exists=False,
        requires_credentials=True,
        rate_limits_known="Unknown",
        fields_available="Unknown",
        limitations="Same OTA category as MakeMyTrip.",
        reason_unavailable=(
            "Not independently fetched this session (see MakeMyTrip note on why a "
            "representative sample was used instead of testing every candidate). Standard OTA "
            "Terms of Use in this category prohibit automated scraping; no public fare API."
        ),
        empirically_tested_this_session=False,
    ),
    SourceProfile(
        name="Amadeus Self-Service Flight Offers Search API",
        domain="developers.amadeus.com",
        access_method="THIRD_PARTY_API",
        robots_txt_status="NOT_INDEPENDENTLY_CHECKED",
        api_exists=True,
        requires_credentials=True,
        rate_limits_known="Free tier exists but is quota-limited (per Amadeus for Developers documentation, subject to change)",
        fields_available="Fare offers including price, cabin, itinerary — a genuinely fare-relevant API, unlike the flight-status APIs below.",
        limitations="Requires registering an application and obtaining an API key/secret (OAuth client credentials) before any request can be made.",
        reason_unavailable=(
            "This is a legitimate, ToS-compliant path to real fare data in principle — but it "
            "requires API credentials this project has not been given. Per the brief's explicit "
            "constraint ('do not use credentials unless explicitly provided/configured'), this "
            "was not registered for or wired up. This is the strongest candidate for the FIRST "
            "real source to connect once credentials are obtained — see docs/scraper.md."
        ),
        empirically_tested_this_session=False,
    ),
    SourceProfile(
        name="Aviationstack API",
        domain="aviationstack.com / apilayer.com",
        access_method="THIRD_PARTY_API",
        robots_txt_status="NOT_INDEPENDENTLY_CHECKED",
        api_exists=True,
        requires_credentials=True,
        rate_limits_known="Free tier exists (per provider's own marketing pages), quota-limited",
        fields_available="Real-time/scheduled flight status and schedule data (departures, arrivals, delays). Does NOT include fare/price data.",
        limitations="Even with a free API key, this API does not return airfare prices at all — wrong data type for this project's index, independent of the credential question.",
        reason_unavailable=(
            "Requires an API key not configured for this project, and — more fundamentally — "
            "does not expose fare/price data even when a key is supplied. Documented here so a "
            "teammate doesn't waste time investigating it as a fare source; it may still be "
            "useful later as a flight-tracking/disruption *context* signal (see "
            "index_engine.context_signals), which is a different use case from fare collection."
        ),
        empirically_tested_this_session=False,
    ),
]


class UnavailableLiveSource(FareSource):
    """Wraps a :class:`SourceProfile` that is currently unavailable —
    returns a structured ``SOURCE_UNAVAILABLE`` result immediately, no
    network call, no attempt to bypass whatever made it unavailable."""

    def __init__(self, profile: SourceProfile) -> None:
        self.name = profile.name
        self.profile = profile

    def search_fares(self, request: SearchRequest) -> SourceCallResult:
        return SourceCallResult(status="SOURCE_UNAVAILABLE", observations=[], error_detail=self.profile.reason_unavailable)


#: What ``ScraperConfig(mode="live")`` uses when the caller doesn't supply
#: its own source list. Every one of these will return SOURCE_UNAVAILABLE
#: today (see module docstring) — a live run is expected to collect zero
#: observations and a run report full of documented, honest failures,
#: which is the correct behaviour until a real source is connected.
LIVE_SOURCES: List[FareSource] = [UnavailableLiveSource(profile) for profile in EVALUATED_SOURCES]
