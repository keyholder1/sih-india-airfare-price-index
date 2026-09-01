"""End-to-end tests for the News & Event Context layer: the
NewsContextService wired to a provider, original-URL preservation,
no-match/multiple-match behaviour, dashboard formatting, and — critically —
that running this layer never changes any index/analytics number."""

from datetime import datetime

import pandas as pd

from index_engine import AirfarePriceIndex, IndexConfig
from index_engine.mock_news_provider import DEMO_ARTICLES, MockNewsProvider
from index_engine.models import IndexResult, RouteIndexResult
from index_engine.news_context import (
    NewsContextConfig,
    NewsContextService,
    attach_news_context,
    is_significant_movement,
    route_movement_from_row,
    to_dashboard_dict,
    to_dashboard_text,
)
from index_engine.news_models import NewsArticle, RouteMovement
from index_engine.news_provider import NewsProvider, NewsSearchQuery
from index_engine.route_analysis import RouteInflationRow

ANCHOR = datetime(2026, 8, 14, 9, 0, 0)


def _movement(change_pct=14.2, origin="BLR", destination="DEL"):
    return RouteMovement(
        route=f"{origin}-{destination}", origin=origin, destination=destination,
        change_pct=change_pct, metric="mom", period="2026-08", as_of=ANCHOR,
    )


class _EmptyProvider(NewsProvider):
    def search(self, query: NewsSearchQuery):
        return []


class _StaticProvider(NewsProvider):
    def __init__(self, articles):
        self._articles = articles

    def search(self, query: NewsSearchQuery):
        return list(self._articles)


# --- basic service wiring ---------------------------------------------------


def test_service_returns_matches_from_demo_mock_provider():
    service = NewsContextService(MockNewsProvider(), config=NewsContextConfig(min_relevance=0.2))
    result = service.get_context(_movement())
    assert isinstance(result.matches, list)
    assert all(m.article.is_mock for m in result.matches)


def test_all_demo_articles_are_labelled_as_mock():
    assert len(DEMO_ARTICLES) > 0
    assert all(a.is_mock is True for a in DEMO_ARTICLES)


# --- no relevant articles ---------------------------------------------------


def test_no_relevant_articles_returns_empty_matches_and_no_factors():
    service = NewsContextService(_EmptyProvider())
    result = service.get_context(_movement())
    assert result.matches == []
    assert result.potential_factors == []
    assert "not a causal explanation" in result.disclaimer.lower() or "coincided" in result.disclaimer.lower() or "context" in result.disclaimer.lower()


def test_no_relevant_articles_dashboard_text_says_none_found():
    service = NewsContextService(_EmptyProvider())
    result = service.get_context(_movement())
    text = to_dashboard_text(result)
    assert "none found" in text.lower()


# --- multiple relevant articles ---------------------------------------------------


def test_multiple_relevant_articles_are_all_surfaced_up_to_top_n():
    articles = [
        NewsArticle(
            headline=f"Article {i}", source="Src", published_at=ANCHOR, url=f"https://example-news.test/{i}",
            event_type="CAPACITY_REDUCTION", related_airports=["BLR", "DEL"], related_routes=["BLR-DEL"],
        )
        for i in range(4)
    ]
    service = NewsContextService(_StaticProvider(articles), config=NewsContextConfig(top_n=5, min_relevance=0.0))
    result = service.get_context(_movement())
    assert len(result.matches) == 4


def test_potential_factors_are_deduplicated_event_types_in_match_order():
    articles = [
        NewsArticle(headline="A", source="S", published_at=ANCHOR, url="https://example-news.test/a",
                    event_type="CAPACITY_REDUCTION", related_routes=["BLR-DEL"]),
        NewsArticle(headline="B", source="S", published_at=ANCHOR, url="https://example-news.test/b",
                    event_type="CAPACITY_REDUCTION", related_routes=["BLR-DEL"]),
        NewsArticle(headline="C", source="S", published_at=ANCHOR, url="https://example-news.test/c",
                    event_type="WEATHER_DISRUPTION", related_airports=["BLR", "DEL"]),
    ]
    service = NewsContextService(_StaticProvider(articles), config=NewsContextConfig(min_relevance=0.0))
    result = service.get_context(_movement())
    assert result.potential_factors.count("CAPACITY_REDUCTION") == 1
    assert set(result.potential_factors) == {"CAPACITY_REDUCTION", "WEATHER_DISRUPTION"}


# --- original URL preservation ---------------------------------------------------


def test_original_article_url_is_preserved_unchanged_through_matching_and_dashboard():
    original_url = "https://original-publisher.example.com/article/2026/08/14/blr-del-capacity"
    article = NewsArticle(
        headline="Capacity cut on BLR-DEL", source="Reuters", published_at=ANCHOR, url=original_url,
        event_type="CAPACITY_REDUCTION", related_routes=["BLR-DEL"],
    )
    service = NewsContextService(_StaticProvider([article]), config=NewsContextConfig(min_relevance=0.0))
    result = service.get_context(_movement())
    assert result.matches[0].article.url == original_url

    dashboard = to_dashboard_dict(result)
    assert dashboard["related_news"][0]["url"] == original_url

    text = to_dashboard_text(result)
    assert original_url in text


def test_no_article_text_is_copied_into_summary_field_beyond_what_was_given():
    # The layer must never invent or expand article body text — the summary
    # it stores/serves is exactly whatever the provider supplied, nothing more.
    article = NewsArticle(
        headline="H", source="S", published_at=ANCHOR, url="https://example-news.test/x",
        event_type="OTHER", summary="short snippet only", related_routes=["BLR-DEL"],
    )
    service = NewsContextService(_StaticProvider([article]), config=NewsContextConfig(min_relevance=0.0))
    result = service.get_context(_movement())
    assert result.matches[0].article.summary == "short snippet only"


# --- dashboard formatting ---------------------------------------------------


def test_dashboard_dict_never_claims_causation():
    service = NewsContextService(MockNewsProvider(), config=NewsContextConfig(min_relevance=0.2))
    result = service.get_context(_movement())
    dashboard = to_dashboard_dict(result)
    disclaimer = dashboard["disclaimer"].lower()
    assert "caused" not in disclaimer
    assert "coincided" in disclaimer or "not a causal" in disclaimer or "not confirmed" in disclaimer


def test_dashboard_text_includes_route_and_change_pct():
    service = NewsContextService(_EmptyProvider())
    result = service.get_context(_movement(change_pct=14.2, origin="BLR", destination="DEL"))
    text = to_dashboard_text(result)
    assert "BLR" in text and "DEL" in text
    assert "14.2" in text


# --- significance threshold ---------------------------------------------------


def test_is_significant_movement_threshold():
    assert is_significant_movement(14.2, threshold_pct=5.0) is True
    assert is_significant_movement(-2.0, threshold_pct=5.0) is False
    assert is_significant_movement(5.0, threshold_pct=5.0) is True


# --- integration with route_analysis output ---------------------------------------------------


def _row(route, mom_pct):
    origin, destination = route.split("-")
    return RouteInflationRow(
        route=route, origin=origin, destination=destination, current_index=110.0,
        mom_inflation_pct=mom_pct, yoy_inflation_pct=None, weight=0.5, traffic_weight=None,
        contribution=None, volatility=None, status="OK",
    )


def test_route_movement_from_row_builds_expected_movement():
    row = _row("BLR-DEL", 14.2)
    movement = route_movement_from_row(row, period="2026-08", as_of=ANCHOR)
    assert movement.route == "BLR-DEL"
    assert movement.change_pct == 14.2
    assert movement.direction == "increase"


def test_route_movement_from_row_returns_none_when_metric_missing():
    row = _row("BLR-DEL", None)
    assert route_movement_from_row(row, period="2026-08", as_of=ANCHOR) is None


def test_attach_news_context_only_runs_for_significant_routes():
    rows = [_row("BLR-DEL", 14.2), _row("BOM-MAA", 1.0), _row("CCU-DEL", -6.0)]
    service = NewsContextService(_EmptyProvider(), config=NewsContextConfig(significance_threshold_pct=5.0))
    results = attach_news_context(rows, period="2026-08", service=service, as_of=ANCHOR)
    assert set(results.keys()) == {"BLR-DEL", "CCU-DEL"}


# --- news never changes the index -------------------------------------------


def test_running_news_context_does_not_change_index_result_values():
    fares = pd.DataFrame(
        [
            {"observation_id": f"o{i}", "airline": "IndiGo", "origin": "BLR", "destination": "DEL",
             "flight_date": "2026-08-15", "booking_date": "2026-08-01", "total_fare": 5000 + i * 10,
             "currency": "INR"}
            for i in range(5)
        ]
    )
    engine = AirfarePriceIndex(base_period="2026-08", config=IndexConfig(base_period="2026-08", min_observations_per_route_period=1))
    before = engine.calculate(fares, current_period="2026-08")
    before_dict = before.to_dict()

    row = _row("BLR-DEL", 14.2)
    service = NewsContextService(MockNewsProvider(), config=NewsContextConfig(min_relevance=0.1))
    _ = attach_news_context([row], period="2026-08", service=service, as_of=ANCHOR)

    after = engine.calculate(fares, current_period="2026-08")
    assert after.to_dict() == before_dict


def test_news_context_result_object_is_not_referenced_by_index_result():
    # Sanity check on the architecture, not just values: IndexResult /
    # RouteIndexResult carry no field that could hold a news object.
    result_fields = set(RouteIndexResult.__dataclass_fields__.keys()) | set(IndexResult.__dataclass_fields__.keys())
    assert not any("news" in f.lower() for f in result_fields)
