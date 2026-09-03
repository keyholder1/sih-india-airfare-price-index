"""Validation tests for the news data model itself (NewsArticle.__post_init__),
independent of matching/ranking behaviour."""

import pytest

from datetime import datetime

from index_engine.news_models import EVENT_TYPES, NewsArticle

ANCHOR = datetime(2026, 8, 14, 9, 0, 0)


def _make(url="https://example-news.test/a", event_type="OTHER"):
    return NewsArticle(headline="H", source="S", published_at=ANCHOR, url=url, event_type=event_type)


def test_valid_article_constructs_without_error():
    article = _make()
    assert article.url == "https://example-news.test/a"


def test_empty_url_is_rejected():
    with pytest.raises(ValueError):
        _make(url="")


def test_url_without_scheme_is_rejected():
    with pytest.raises(ValueError):
        _make(url="example-news.test/a")


def test_non_http_scheme_is_rejected():
    with pytest.raises(ValueError):
        _make(url="ftp://example-news.test/a")


def test_javascript_scheme_url_is_rejected():
    # Defensive: a malformed/hostile "url" should never survive into a
    # dashboard's "Read original article" link.
    with pytest.raises(ValueError):
        _make(url="javascript:alert(1)")


def test_all_declared_event_types_are_accepted():
    for event_type in EVENT_TYPES:
        _make(event_type=event_type)  # must not raise


def test_unknown_event_type_is_rejected():
    with pytest.raises(ValueError):
        _make(event_type="NOT_A_REAL_EVENT_TYPE")
