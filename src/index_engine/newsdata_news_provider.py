"""Real :class:`NewsProvider` backed by newsdata.io's REST API
(https://newsdata.io/api/1/latest). See news_provider.py's module
docstring: this is the seam a teammate implements to connect a real
feed -- MockNewsProvider remains for tests/demos.

The free tier's ``/latest`` endpoint has no server-side date-range
filter (that's a paid ``/archive`` feature), so this provider fetches by
keyword/country/language and filters to ``query``'s date window itself;
nothing outside that window is returned even if newsdata.io includes it.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import List, Optional

import httpx

from .news_models import EventType, NewsArticle
from .news_provider import NewsProvider, NewsSearchQuery

NEWSDATA_ENDPOINT = "https://newsdata.io/api/1/latest"
REQUEST_TIMEOUT_SECONDS = 15.0
#: Comma-separated to support multiple keys -- see _api_keys_from_env.
ENV_API_KEY = "NEWSDATA_API_KEY"

#: newsdata.io's own error codes for "this key is out of quota / invalid"
#: (as opposed to a malformed request, which retrying with another key
#: can't fix). HTTP 429 is also always treated as a quota signal.
_ROTATE_ON_ERROR_CODES = {"RateLimitExceeded", "UnauthorizedRateLimitedError", "APIKeyExhausted", "UnauthorizedError"}

#: Same best-effort real-headline -> controlled-vocabulary classification
#: as gdelt_news_provider.py -- see that module's docstring for why this
#: is a categorisation of real text, never a fabricated claim.
_EVENT_KEYWORDS: List[tuple] = [
    ("STRIKE", ("strike", "protest", "walkout")),
    ("WEATHER_DISRUPTION", ("fog", "rain", "storm", "weather", "cyclone", "monsoon", "visibility")),
    ("FUEL_PRICE_CHANGE", ("atf", "fuel price", "jet fuel")),
    ("FLIGHT_CANCELLATION", ("cancel", "grounded", "grounds flights")),
    ("CAPACITY_REDUCTION", ("capacity cut", "trims capacity", "reduces flights", "frequency cut")),
    ("REGULATORY_CHANGE", ("dgca", "ministry of civil aviation", "regulation", "policy")),
    ("GEOPOLITICAL_EVENT", ("airspace closure", "sanctions", "conflict", "war")),
    ("AIRPORT_DISRUPTION", ("airport shut", "runway", "air traffic control", "atc")),
]


def _classify(text: str) -> EventType:
    lower = text.lower()
    for event_type, keywords in _EVENT_KEYWORDS:
        if any(k in lower for k in keywords):
            return event_type  # type: ignore[return-value]
    return "OTHER"


def _parse_pub_date(raw: str) -> Optional[datetime]:
    # newsdata.io's pubDate is "YYYY-MM-DD HH:MM:SS", pubDateTZ is "UTC".
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _api_keys_from_env() -> List[str]:
    raw = os.environ.get(ENV_API_KEY, "")
    return [k.strip() for k in raw.split(",") if k.strip()]


class NewsdataNewsProvider(NewsProvider):
    """Queries newsdata.io's /latest endpoint for real news, filtered to
    the requested date window client-side (see module docstring). Never
    raises on a network/parse/auth failure -- a flaky or unconfigured
    external call degrades to "no candidates found," not a broken page.

    Supports multiple keys (NEWSDATA_API_KEY as a comma-separated list,
    or ``api_keys`` passed directly): each ``search()`` call tries them
    in order and rotates to the next one on a quota/auth-style failure
    (see _ROTATE_ON_ERROR_CODES), so one key running out doesn't take
    the whole feature down. A genuinely malformed request (bad query
    syntax etc.) is not retried across keys -- that would just repeat
    the same failure ``len(keys)`` times.
    """

    def __init__(self, api_keys: Optional[List[str]] = None, client: Optional[httpx.Client] = None) -> None:
        self._api_keys = api_keys if api_keys is not None else _api_keys_from_env()
        self._client = client

    def _build_query(self, query: NewsSearchQuery) -> str:
        # Route/airport/city keywords alone are too generic (e.g. "Delhi"
        # matches unrelated politics/court news) -- AND-ing in an aviation
        # term keeps recall broad within the aviation domain rather than
        # narrowing to an exact route, which news_matching re-scores anyway.
        terms = list(dict.fromkeys(query.keywords))[:5]  # newsdata's q has a length limit
        clause = " OR ".join(terms) if terms else "India"
        return f"({clause}) AND (flight OR airline OR airfare OR aviation)"

    def _fetch(self, api_key: str, q: str) -> tuple[Optional[dict], bool]:
        """Returns (payload_or_None, should_rotate_to_next_key)."""
        params = {"apikey": api_key, "q": q, "country": "in", "language": "en"}
        try:
            client = self._client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
            response = client.get(NEWSDATA_ENDPOINT, params=params)
        except httpx.HTTPError:
            return None, False  # network-level failure -- another key won't help
        finally:
            if self._client is None:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass

        if response.status_code == 429:
            return None, True
        try:
            payload = response.json()
        except ValueError:
            return None, False

        if payload.get("status") != "success":
            code = (payload.get("results") or {}).get("code") if isinstance(payload.get("results"), dict) else None
            return None, response.status_code in (401, 403) or code in _ROTATE_ON_ERROR_CODES
        return payload, False

    def search(self, query: NewsSearchQuery) -> List[NewsArticle]:
        if not self._api_keys:
            return []

        q = self._build_query(query)
        payload = None
        for api_key in self._api_keys:
            payload, rotate = self._fetch(api_key, q)
            if payload is not None:
                break
            if not rotate:
                return []  # a failure no key rotation can fix
        if payload is None:
            return []  # every key exhausted/invalid

        articles: List[NewsArticle] = []
        for raw in payload.get("results", []) or []:
            url = raw.get("link")
            title = raw.get("title")
            published_at = _parse_pub_date(raw.get("pubDate", ""))
            if not url or not title or published_at is None:
                continue
            if not (query.start_date <= published_at <= query.end_date):
                continue  # outside the requested window -- see module docstring
            try:
                articles.append(
                    NewsArticle(
                        headline=title,
                        source=raw.get("source_name") or raw.get("source_id") or "unknown",
                        published_at=published_at,
                        url=url,
                        event_type=_classify(f"{title} {raw.get('description') or ''}"),
                        summary=(raw.get("description") or None),
                        is_mock=False,
                    )
                )
            except ValueError:
                continue  # NewsArticle.__post_init__ rejected e.g. a malformed URL
        return articles
