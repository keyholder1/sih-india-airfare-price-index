"""Real :class:`NewsProvider` backed by NewsAPI.org's ``/v2/everything``
endpoint (https://newsapi.org/v2/everything). See news_provider.py's
module docstring: this is the seam a teammate implements to connect a
real feed -- MockNewsProvider remains for tests/demos.

Verified against a real live response during this project's recon
(2026-09-04, ``q=airfare India``): the free tier returns full articles
(headline, description, url, publishedAt, source name) but rejects a
``from`` date older than ~1 month with HTTP 426 ("upgrade required" per
NewsAPI.org's own developer-plan restriction) -- callers past that
window get an empty result, never a fabricated one.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from .news_models import EventType, NewsArticle
from .news_provider import NewsProvider, NewsSearchQuery

NEWSAPI_ORG_ENDPOINT = "https://newsapi.org/v2/everything"
REQUEST_TIMEOUT_SECONDS = 15.0
ENV_API_KEY = "NEWSAPI_ORG_API_KEY"
PAGE_SIZE = 20

#: Same best-effort real-headline -> controlled-vocabulary classification
#: as gdelt_news_provider.py / newsdata_news_provider.py -- see those
#: modules' docstrings for why this is a categorisation of real text,
#: never a fabricated claim.
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


def _parse_published_at(raw: str) -> Optional[datetime]:
    # NewsAPI.org's publishedAt is ISO-8601 with a "Z" suffix.
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None


class NewsApiOrgProvider(NewsProvider):
    """Queries NewsAPI.org's /v2/everything endpoint for real news. Never
    raises on a network/parse/auth/quota failure -- a flaky or
    unconfigured external call degrades to "no candidates found," not a
    broken page (see module docstring for the free tier's ~1-month
    lookback limit specifically)."""

    def __init__(self, api_key: Optional[str] = None, client: Optional[httpx.Client] = None) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get(ENV_API_KEY)
        self._client = client

    def _build_query(self, query: NewsSearchQuery) -> str:
        # Same reasoning as NewsdataNewsProvider._build_query: bare
        # route/airport/city keywords are too generic on their own (e.g.
        # "Delhi" matches unrelated politics/court news), so an aviation
        # term is AND-ed in to keep recall inside the aviation domain --
        # news_matching re-scores everything returned anyway.
        terms = list(dict.fromkeys(query.keywords))[:6]
        clause = " OR ".join(terms) if terms else "India"
        return f"({clause}) AND (flight OR airline OR airfare OR aviation)"

    def search(self, query: NewsSearchQuery) -> List[NewsArticle]:
        if not self._api_key:
            return []

        params = {
            "q": self._build_query(query),
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": PAGE_SIZE,
            "from": query.start_date.date().isoformat(),
            "to": query.end_date.date().isoformat(),
            "apiKey": self._api_key,
        }

        try:
            client = self._client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
            response = client.get(NEWSAPI_ORG_ENDPOINT, params=params)
        except httpx.HTTPError:
            return []
        finally:
            if self._client is None:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass

        if response.status_code != 200:
            return []
        try:
            payload = response.json()
        except ValueError:
            return []
        if payload.get("status") != "ok":
            return []

        articles: List[NewsArticle] = []
        for raw in payload.get("articles", []) or []:
            url = raw.get("url")
            title = raw.get("title")
            published_at = _parse_published_at(raw.get("publishedAt", ""))
            if not url or not title or published_at is None:
                continue
            if not (query.start_date <= published_at.replace(tzinfo=None) <= query.end_date):
                continue
            source = (raw.get("source") or {}).get("name") or "unknown"
            try:
                articles.append(
                    NewsArticle(
                        headline=title,
                        source=source,
                        published_at=published_at,
                        url=url,
                        event_type=_classify(f"{title} {raw.get('description') or ''}"),
                        summary=raw.get("description") or None,
                        is_mock=False,
                    )
                )
            except ValueError:
                continue  # NewsArticle.__post_init__ rejected e.g. a malformed URL
        return articles
