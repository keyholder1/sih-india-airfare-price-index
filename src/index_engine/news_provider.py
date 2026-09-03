"""Provider interface for the News & Event Context layer.

``NewsProvider`` is the seam a teammate implements to connect a real news
API/feed (NewsAPI.org, GNews, a licensed Reuters/PTI feed, an internal
scraper...). Nothing else in this package needs to know or care which
concrete provider is wired in — :mod:`news_matching` and :mod:`news_context`
only ever talk to this abstract interface.

To add a real provider: subclass ``NewsProvider``, implement ``search``,
call the real API, and map its results to ``NewsArticle`` objects
(``is_mock=False``). No other file in this package needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

from .news_models import NewsArticle


@dataclass
class NewsSearchQuery:
    """What :meth:`NewsProvider.search` is asked to look for.

    Providers are expected to do a broad, recall-oriented search (an OR of
    keywords over the date window) — precise relevance ranking against a
    specific route movement happens afterwards in :mod:`news_matching`, not
    inside the provider.
    """

    keywords: List[str]
    start_date: datetime
    end_date: datetime
    airports: List[str] = field(default_factory=list)
    airlines: List[str] = field(default_factory=list)
    routes: List[str] = field(default_factory=list)


class NewsProvider(ABC):
    """Abstract source of :class:`NewsArticle` objects."""

    @abstractmethod
    def search(self, query: NewsSearchQuery) -> List[NewsArticle]:
        """Return candidate articles for ``query``.

        Implementations should filter by date range at minimum; keyword/
        airport/airline/route filtering can be as loose as the underlying
        API allows since :mod:`news_matching` re-scores every candidate
        against the actual route movement.
        """
        raise NotImplementedError
