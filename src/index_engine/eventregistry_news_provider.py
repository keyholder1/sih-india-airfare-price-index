"""Real :class:`NewsProvider` backed by Event Registry / newsapi.ai's
article search endpoint (https://eventregistry.org/api/v1/article/getArticles).
See news_provider.py's module docstring: this is the seam a teammate
implements to connect a real feed -- MockNewsProvider remains for
tests/demos.

Response schema verified against a real live call during this project's
recon (2026-09-04, ``keyword="airfare India"``, ``dateStart``/``dateEnd``
narrowed the window server-side):

    {
      "articles": {
        "results": [
          {"uri": "...", "date": "YYYY-MM-DD", "dateTimePub": "...Z",
           "url": "...", "title": "...", "body": "...",
           "source": {"uri": "...", "title": "..."},
           "isDuplicate": false, "lang": "eng", ...},
          ...
        ],
        "totalResults": <int>
      }
    }

An invalid/missing API key returns a plain-text (not JSON) error body
with HTTP 401 -- handled the same as any other unusable response: no
candidates, never a fabricated one.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from .news_models import EventType, NewsArticle
from .news_provider import NewsProvider, NewsSearchQuery

EVENTREGISTRY_ENDPOINT = "https://eventregistry.org/api/v1/article/getArticles"
REQUEST_TIMEOUT_SECONDS = 15.0
ENV_API_KEY = "EVENTREGISTRY_API_KEY"
ARTICLES_COUNT = 20

#: Same best-effort real-headline -> controlled-vocabulary classification
#: as the other real providers in this package -- see their docstrings.
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


def _parse_datetime(raw: str) -> Optional[datetime]:
    # dateTimePub / dateTime are ISO-8601 with a "Z" suffix; dateTimePub
    # is sometimes absent, "date" (YYYY-MM-DD only) is the fallback.
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None


class EventRegistryNewsProvider(NewsProvider):
    """Queries Event Registry's (newsapi.ai) article search endpoint for
    real news. Never raises on a network/parse/auth failure -- a flaky or
    unconfigured external call degrades to "no candidates found," not a
    broken page."""

    def __init__(self, api_key: Optional[str] = None, client: Optional[httpx.Client] = None) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get(ENV_API_KEY)
        self._client = client

    def _build_keyword(self, query: NewsSearchQuery) -> str:
        # Event Registry's `keyword` is a single free-text string (OR'd
        # internally on whitespace-separated phrases isn't supported the
        # way newsdata's boolean `q` is) -- keep it to the most specific
        # terms plus one aviation anchor so results stay in-domain.
        terms = list(dict.fromkeys(query.keywords))[:4]
        return " ".join(terms + ["airfare"]) if terms else "India airfare"

    def search(self, query: NewsSearchQuery) -> List[NewsArticle]:
        if not self._api_key:
            return []

        body = {
            "action": "getArticles",
            "keyword": self._build_keyword(query),
            "dateStart": query.start_date.date().isoformat(),
            "dateEnd": query.end_date.date().isoformat(),
            "lang": "eng",
            "articlesPage": 1,
            "articlesCount": ARTICLES_COUNT,
            "articlesSortBy": "date",
            "articlesSortByAsc": False,
            "articleBodyLen": 300,
            "resultType": "articles",
            "dataType": ["news"],
            "apiKey": self._api_key,
        }

        try:
            client = self._client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
            response = client.post(EVENTREGISTRY_ENDPOINT, json=body)
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
            return []  # e.g. the plain-text auth-error body, not JSON

        results = ((payload.get("articles") or {}).get("results")) or []

        articles: List[NewsArticle] = []
        for raw in results:
            if raw.get("isDuplicate"):
                continue
            url = raw.get("url")
            title = raw.get("title")
            published_at = _parse_datetime(raw.get("dateTimePub") or raw.get("dateTime") or "")
            if published_at is None and raw.get("date"):
                published_at = _parse_datetime(f"{raw['date']}T00:00:00Z")
            if not url or not title or published_at is None:
                continue
            if not (query.start_date <= published_at.replace(tzinfo=None) <= query.end_date):
                continue
            source_name = (raw.get("source") or {}).get("title") or (raw.get("source") or {}).get("uri") or "unknown"
            try:
                articles.append(
                    NewsArticle(
                        headline=title,
                        source=source_name,
                        published_at=published_at,
                        url=url,
                        event_type=_classify(f"{title} {raw.get('body') or ''}"),
                        summary=(raw.get("body") or None),
                        is_mock=False,
                    )
                )
            except ValueError:
                continue  # NewsArticle.__post_init__ rejected e.g. a malformed URL
        return articles
