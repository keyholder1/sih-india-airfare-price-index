"""Postgres-backed caching wrapper around a :class:`NewsProvider`.

Lives in ``src.engine`` (the infrastructure layer that's allowed to touch
``db.py``), not ``index_engine`` (kept dependency-free/pure) -- same
layering as the rest of this package, see ``data_access.py``.

Caches one calendar week per (route, generic-keyword) query so that
looking at the same route's news repeatedly within a week never spends
real API quota again -- the provider it wraps (typically a
``CompositeNewsProvider`` fanning out to every configured real source)
is only actually called once per route per week.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from index_engine.news_models import NewsArticle
from index_engine.news_provider import NewsProvider, NewsSearchQuery

from . import db


def _cache_key(query: NewsSearchQuery, now: datetime) -> str:
    # query.routes carries [movement.route] (see news_context._build_search_query);
    # fall back to the first couple of keywords for a caller that doesn't
    # set routes, so this never collapses every query onto one key.
    subject = "-".join(sorted(query.routes)) if query.routes else "-".join(sorted(query.keywords[:2]))
    iso_year, iso_week, _ = now.isocalendar()
    return f"{subject}::{iso_year}-W{iso_week:02d}"


def _article_from_dict(d: dict) -> NewsArticle:
    published_at = d["published_at"]
    if isinstance(published_at, str):
        published_at = datetime.fromisoformat(published_at)
    return NewsArticle(
        headline=d["headline"],
        source=d["source"],
        published_at=published_at,
        url=d["url"],
        event_type=d["event_type"],
        summary=d.get("summary"),
        related_airlines=d.get("related_airlines") or [],
        related_airports=d.get("related_airports") or [],
        related_routes=d.get("related_routes") or [],
        confidence_score=d.get("confidence_score"),
        is_mock=d.get("is_mock", False),
    )


class CachingNewsProvider(NewsProvider):
    """Wraps ``inner`` (usually a multi-source ``CompositeNewsProvider``)
    with a one-week Postgres cache, keyed by route. Falls through to
    calling ``inner`` directly, uncached, when Postgres isn't configured
    -- same fallback posture as the rest of this project (see
    data_access.py): a missing database degrades a feature, never breaks
    it.
    """

    def __init__(self, inner: NewsProvider) -> None:
        self._inner = inner

    def search(self, query: NewsSearchQuery) -> List[NewsArticle]:
        if not db.is_configured():
            return self._inner.search(query)

        key = _cache_key(query, datetime.now(timezone.utc))
        try:
            cached = db.get_cached_news(key)
        except Exception:  # noqa: BLE001 -- a cache-read failure must not break the feature
            cached = None
        if cached is not None:
            return [_article_from_dict(a) for a in cached]

        articles = self._inner.search(query)
        try:
            db.set_cached_news(key, [a.to_dict() for a in articles])
        except Exception:  # noqa: BLE001 -- a cache-write failure must not break the feature
            pass
        return articles
