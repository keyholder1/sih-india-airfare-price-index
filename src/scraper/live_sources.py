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

from .indigo_source import IndiGoSource
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
        robots_txt_status="NOT_INDEPENDENTLY_CHECKED",
        api_exists=True,
        requires_credentials=True,
        rate_limits_known="Not yet confirmed — depends on the developer/NDC program tier granted",
        fields_available="Not yet confirmed — depends on the granted API's actual response schema",
        limitations=(
            "IndiGo operates a real developer/NDC API program (updated finding, superseding "
            "the earlier 'no public API' assessment). Production access is understood to "
            "involve an approval/business process, not instant self-service signup."
        ),
        reason_unavailable=(
            "This is currently the strongest airline-specific candidate for a real source. "
            "scraper.indigo_source.IndiGoSource is a credential-driven scaffold ready to "
            "receive real API access, but no approved credentials or verified request/response "
            "contract exist yet in this project -- see docs/scraper.md 'Adding a real source "
            "later'. Do not fabricate the endpoint, auth flow, or response shape; complete "
            "IndiGoSource._call_api only once real, verified API documentation is obtained."
        ),
        empirically_tested_this_session=False,
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
        limitations=(
            "MakeMyTrip's 'myPartner' program is a B2B/travel-agent platform, not a public "
            "self-service developer fare API -- it is not automatically available just by "
            "signing up. Any programmatic fare access would require a proper authorized "
            "business relationship, not a self-service key."
        ),
        reason_unavailable=(
            "An automated fetch of https://www.makemytrip.com/robots.txt timed out during "
            "evaluation, consistent with bot-protection. MakeMyTrip's Terms of Use prohibit "
            "automated scraping/data-mining of the site (standard OTA ToS clause). Do not "
            "reverse-engineer internal endpoints or use unofficial/unauthorized APIs for this "
            "source under any circumstance."
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
        limitations=(
            "Same OTA category as MakeMyTrip. IMPORTANT: earlier project notes referenced a "
            "possible public/self-service Cleartrip fare API with specific endpoints/headers -- "
            "those claims were never independently verified and must not be treated as fact. "
            "Do not build or assume any Cleartrip adapter against unverified documentation."
        ),
        reason_unavailable=(
            "Not independently fetched this session (see MakeMyTrip note on why a "
            "representative sample was used instead of testing every candidate). Standard OTA "
            "Terms of Use in this category prohibit automated scraping; no verified public fare "
            "API. If real, authorized Cleartrip API credentials/documentation become available "
            "later, implement against that real contract only -- never invented endpoints."
        ),
        empirically_tested_this_session=False,
    ),
    SourceProfile(
        name="Amadeus Self-Service Flight Offers Search API",
        domain="developers.amadeus.com",
        access_method="THIRD_PARTY_API",
        robots_txt_status="NOT_INDEPENDENTLY_CHECKED",
        api_exists=False,
        requires_credentials=True,
        rate_limits_known="N/A — self-service registration portal has since been shut down",
        fields_available="N/A",
        limitations=(
            "UPDATED FINDING: the Amadeus self-service developer portal this project previously "
            "identified as the strongest first-real-source candidate has since been shut down. "
            "New self-service registration is not currently possible. Do not build this project "
            "around Amadeus self-service access, and do not assume credentials can currently be "
            "obtained through it."
        ),
        reason_unavailable=(
            "Self-service registration path no longer available. If Amadeus reopens self-service "
            "access, or a commercial/partner agreement is separately arranged, this entry should "
            "be re-evaluated -- but it is not a near-term source for this project."
        ),
        empirically_tested_this_session=False,
    ),
    SourceProfile(
        name="Duffel API",
        domain="duffel.com",
        access_method="THIRD_PARTY_API",
        robots_txt_status="NOT_INDEPENDENTLY_CHECKED",
        api_exists=True,
        requires_credentials=True,
        rate_limits_known="Not yet confirmed for this project's usage tier",
        fields_available=(
            "Genuine flight offer search (fares, itineraries) via a documented developer API. "
            "Sandbox mode uses a fictional 'Duffel Airways' test airline -- sandbox results must "
            "never be represented as real Indian market fares."
        ),
        limitations=(
            "Production access requires verification/commercial terms. Indian domestic airline "
            "coverage in production is not confirmed for this project -- do not claim it works "
            "for Indian routes until actually tested against a real production credential."
        ),
        reason_unavailable=(
            "Legitimate developer API with a real sandbox, but no credentials (sandbox or "
            "production) have been configured for this project, and Indian domestic coverage is "
            "unverified. A reasonable optional future adapter once someone registers and "
            "confirms Indian route coverage -- see docs/scraper.md."
        ),
        empirically_tested_this_session=False,
    ),
    SourceProfile(
        name="Travelpayouts / Aviasales",
        domain="travelpayouts.com",
        access_method="THIRD_PARTY_API",
        robots_txt_status="NOT_INDEPENDENTLY_CHECKED",
        api_exists=True,
        requires_credentials=True,
        rate_limits_known="Not yet confirmed",
        fields_available=(
            "Likely cached/aggregated fare data rather than a live shopping quote -- this "
            "distinction is unconfirmed and must be verified before any data from this source "
            "is presented as equivalent to a live scraped fare."
        ),
        limitations=(
            "Indian domestic route coverage is not confirmed. If ever implemented, any data "
            "from this source must be clearly labelled as cached/aggregated, not live, unless "
            "proven otherwise."
        ),
        reason_unavailable=(
            "Worth investigating further, but no credentials are configured and neither "
            "Indian coverage nor live-vs-cached data freshness has been verified. Not wired up "
            "until both are confirmed."
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


#: Sources with an actual credential-gated adapter (not just a static
#: profile wrapper) -- currently only IndiGo. Still returns
#: SOURCE_UNAVAILABLE today (see IndiGoSource docstring), but for the
#: real reason "no verified API contract/credentials yet," decided at
#: call time, not hard-coded per instance.
_ADAPTER_SOURCES_BY_NAME = {
    "IndiGo": IndiGoSource,
}

#: What ``ScraperConfig(mode="live")`` uses when the caller doesn't supply
#: its own source list. Every one of these will return SOURCE_UNAVAILABLE
#: today (see module docstring) — a live run is expected to collect zero
#: observations and a run report full of documented, honest failures,
#: which is the correct behaviour until a real source is connected.
LIVE_SOURCES: List[FareSource] = [
    _ADAPTER_SOURCES_BY_NAME[profile.name]() if profile.name in _ADAPTER_SOURCES_BY_NAME else UnavailableLiveSource(profile)
    for profile in EVALUATED_SOURCES
]
