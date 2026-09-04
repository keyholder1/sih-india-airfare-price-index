"""Fans a search out to several :class:`NewsProvider` implementations and
merges their results into one candidate list -- lets the News & Event
Context layer draw on every real news source configured (newsdata.io,
NewsAPI.org, Event Registry/newsapi.ai, GDELT, ...) instead of picking
just one, while :mod:`news_matching`'s relevance scoring stays the only
thing deciding which of them actually surface. Nothing downstream needs
to know or care how many underlying providers contributed.
"""

from __future__ import annotations

from typing import List

from .news_models import NewsArticle
from .news_provider import NewsProvider, NewsSearchQuery


class CompositeNewsProvider(NewsProvider):
    """Queries every wrapped provider and returns the union of their
    articles, de-duplicated by URL (first occurrence wins). One
    provider's failure/timeout never blocks the others -- each provider
    already degrades to an empty list on its own failure (see e.g.
    NewsdataNewsProvider, NewsApiOrgProvider), so a bad provider here
    just contributes nothing rather than raising."""

    def __init__(self, providers: List[NewsProvider]) -> None:
        self._providers = providers

    def search(self, query: NewsSearchQuery) -> List[NewsArticle]:
        seen_urls: set = set()
        merged: List[NewsArticle] = []
        for provider in self._providers:
            try:
                candidates = provider.search(query)
            except Exception:  # noqa: BLE001 -- one provider's bug must not sink the others
                continue
            for article in candidates:
                if article.url in seen_urls:
                    continue
                seen_urls.add(article.url)
                merged.append(article)
        return merged
