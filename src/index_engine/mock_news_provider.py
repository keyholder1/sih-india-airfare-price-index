"""A local, fully-fabricated :class:`NewsProvider` for tests and demos.

Every article below is MOCK DATA — invented for this project to exercise
the matching logic end-to-end without a real news API key. It is not a
record of anything that actually happened. Every article carries
``is_mock=True`` so it can never be confused with a real result once a real
provider is wired in (see :mod:`news_provider`).

Do not add real, uncredited news content here. When a real provider is
connected, use it instead of this one; this class exists purely so the
News & Event Context layer has something to run against in tests and in
the SIH demo.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from .news_models import NewsArticle
from .news_provider import NewsProvider, NewsSearchQuery


def _mock_article(
    headline: str,
    source: str,
    days_offset: int,
    url: str,
    event_type: str,
    summary: str,
    airlines: Optional[List[str]] = None,
    airports: Optional[List[str]] = None,
    routes: Optional[List[str]] = None,
    anchor: datetime = datetime(2026, 8, 14, 9, 0, 0),
) -> NewsArticle:
    return NewsArticle(
        headline=headline,
        source=source,
        published_at=anchor + timedelta(days=days_offset),
        url=url,
        event_type=event_type,
        summary=summary,
        related_airlines=airlines or [],
        related_airports=airports or [],
        related_routes=routes or [],
        is_mock=True,
    )


#: Fabricated demo/test fixture data. Anchored around 2026-08-14 to line up
#: with the BLR->DEL example used throughout docs/news_context.md — dates
#: are illustrative only, not real reporting dates.
DEMO_ARTICLES: List[NewsArticle] = [
    _mock_article(
        headline="[MOCK] Airline trims Bengaluru-Delhi capacity ahead of peak season",
        source="Mock Aviation Wire",
        days_offset=-1,
        url="https://example-news.test/mock/blr-del-capacity-cut",
        event_type="CAPACITY_REDUCTION",
        summary="A major domestic carrier reduced daily frequencies on the Bengaluru-Delhi trunk route, citing aircraft availability.",
        airlines=["IndiGo"],
        airports=["BLR", "DEL"],
        routes=["BLR-DEL"],
    ),
    _mock_article(
        headline="[MOCK] Heavy monsoon rain disrupts Delhi airport operations",
        source="Mock Daily Herald",
        days_offset=0,
        url="https://example-news.test/mock/del-weather-disruption",
        event_type="WEATHER_DISRUPTION",
        summary="Waterlogging and low visibility at Delhi's IGI airport led to dozens of delays and a handful of diversions.",
        airlines=[],
        airports=["DEL"],
        routes=[],
    ),
    _mock_article(
        headline="[MOCK] Ground staff strike grounds several flights nationwide",
        source="Mock Press Bureau",
        days_offset=1,
        url="https://example-news.test/mock/nationwide-strike",
        event_type="STRIKE",
        summary="A one-day strike by ground-handling staff caused cancellations at multiple metro airports.",
        airlines=["Air India"],
        airports=["DEL", "BOM"],
        routes=[],
    ),
    _mock_article(
        headline="[MOCK] Jet fuel prices climb for second straight month",
        source="Mock Business Desk",
        days_offset=-5,
        url="https://example-news.test/mock/atf-price-hike",
        event_type="FUEL_PRICE_CHANGE",
        summary="ATF prices rose again this cycle, adding pressure on domestic carriers' operating costs.",
        airlines=[],
        airports=[],
        routes=[],
    ),
    _mock_article(
        headline="[MOCK] Regulator proposes new domestic route dispersal rules",
        source="Mock Policy Tracker",
        days_offset=-20,
        url="https://example-news.test/mock/route-dispersal-rules",
        event_type="REGULATORY_CHANGE",
        summary="A draft circular would revise how regional connectivity slots are allocated among domestic carriers.",
        airlines=[],
        airports=[],
        routes=[],
    ),
    _mock_article(
        headline="[MOCK] Fog forces multiple flight cancellations at Delhi airport",
        source="Mock Metro Times",
        days_offset=2,
        url="https://example-news.test/mock/del-fog-cancellations",
        event_type="FLIGHT_CANCELLATION",
        summary="Dense fog led several carriers to cancel early-morning departures out of Delhi.",
        airlines=["Vistara"],
        airports=["DEL"],
        routes=[],
    ),
]


class MockNewsProvider(NewsProvider):
    """Serves fixture ``NewsArticle`` data. Never call this in production —
    it exists so the rest of the layer can be built, tested, and demoed
    before a real news API is connected.
    """

    def __init__(self, articles: Optional[List[NewsArticle]] = None) -> None:
        self._articles = articles if articles is not None else list(DEMO_ARTICLES)

    def search(self, query: NewsSearchQuery) -> List[NewsArticle]:
        results = []
        for article in self._articles:
            if not (query.start_date <= article.published_at <= query.end_date):
                continue
            results.append(article)
        return results
