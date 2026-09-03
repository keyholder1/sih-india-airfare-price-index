"""Real :class:`NewsProvider` backed by GDELT's free, keyless DOC 2.0 API
(https://api.gdeltproject.org/api/v2/doc/doc). See news_provider.py's
module docstring: this is the seam a teammate implements to connect a
real feed -- MockNewsProvider remains for tests/demos, this is what the
running API actually uses.

GDELT indexes a huge range of outlets by crawling, not curating -- recall
is broad but noisier than a curated wire feed. Every article returned
here is genuinely real (``is_mock=False``); GDELT gives no full-text
snippet in list mode, so ``summary`` stays ``None`` rather than
fabricating one from the headline.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

import httpx

from .news_models import EventType, NewsArticle
from .news_provider import NewsProvider, NewsSearchQuery

GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_RECORDS = 20

#: Lightweight keyword -> EventType classification. GDELT gives a headline
#: and nothing else structured, so this is a best-effort categorisation of
#: real article text into the existing controlled vocabulary -- never a
#: claim about what actually happened, just where in the taxonomy a real
#: headline plausibly belongs. Unmatched headlines get "OTHER", never
#: guessed into a specific category with no textual basis.
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


def _classify(headline: str) -> EventType:
    lower = headline.lower()
    for event_type, keywords in _EVENT_KEYWORDS:
        if any(k in lower for k in keywords):
            return event_type  # type: ignore[return-value]
    return "OTHER"


def _parse_seendate(raw: str) -> Optional[datetime]:
    # GDELT's seendate is "YYYYMMDDHHMMSS" UTC.
    try:
        return datetime.strptime(raw, "%Y%m%d%H%M%S").replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


class GdeltNewsProvider(NewsProvider):
    """Queries GDELT's DOC 2.0 API for real news matching the search
    window. Never raises on a network/parse failure -- a flaky external
    call degrades to "no candidates found" for this route, not a broken
    page; see search()'s except clauses."""

    def __init__(self, client: Optional[httpx.Client] = None, source_country: Optional[str] = "IN") -> None:
        self._client = client
        self._source_country = source_country

    def _build_query(self, query: NewsSearchQuery) -> str:
        terms = list(dict.fromkeys(query.keywords))[:8]  # de-dup, cap query length
        clause = " OR ".join(f'"{t}"' for t in terms if t)
        q = f"({clause}) aviation" if clause else "aviation India"
        if self._source_country:
            q += f" sourcecountry:{self._source_country}"
        return q

    def search(self, query: NewsSearchQuery) -> List[NewsArticle]:
        params = {
            "query": self._build_query(query),
            "mode": "artlist",
            "maxrecords": str(MAX_RECORDS),
            "format": "json",
            "startdatetime": query.start_date.strftime("%Y%m%d%H%M%S"),
            "enddatetime": query.end_date.strftime("%Y%m%d%H%M%S"),
        }
        try:
            client = self._client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
            response = client.get(GDELT_ENDPOINT, params=params, headers={"User-Agent": "sih-airfare-index/0.1"})
            if response.status_code != 200:
                return []
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        finally:
            if self._client is None:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass

        articles: List[NewsArticle] = []
        for raw in payload.get("articles", []):
            url = raw.get("url")
            title = raw.get("title")
            seendate = _parse_seendate(raw.get("seendate", ""))
            if not url or not title or seendate is None:
                continue
            try:
                articles.append(
                    NewsArticle(
                        headline=title,
                        source=raw.get("domain") or "unknown",
                        published_at=seendate,
                        url=url,
                        event_type=_classify(title),
                        summary=None,
                        is_mock=False,
                    )
                )
            except ValueError:
                # NewsArticle.__post_init__ rejects a malformed URL etc. --
                # skip that one candidate, never let it sink the whole batch.
                continue
        return articles
