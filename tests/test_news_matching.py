"""Tests for the news relevance-matching signals in isolation:
route matching, airport matching, airline matching, date-window matching,
and relevance ranking. Uses hand-built NewsArticle fixtures, not the mock
provider's demo data, so each signal can be tested independently."""

from datetime import datetime, timedelta

from index_engine.news_matching import MatchingConfig, rank_articles, score_article
from index_engine.news_models import NewsArticle, RouteMovement

ANCHOR = datetime(2026, 8, 14, 9, 0, 0)


def _movement(change_pct=14.2, origin="BLR", destination="DEL", as_of=ANCHOR):
    return RouteMovement(
        route=f"{origin}-{destination}", origin=origin, destination=destination,
        change_pct=change_pct, metric="mom", period="2026-08", as_of=as_of,
    )


def _article(
    headline="Test headline",
    days_offset=0,
    event_type="CAPACITY_REDUCTION",
    airports=None,
    airlines=None,
    routes=None,
    url="https://example-news.test/a1",
):
    return NewsArticle(
        headline=headline, source="Test Source", published_at=ANCHOR + timedelta(days=days_offset),
        url=url, event_type=event_type, summary="A test summary.",
        related_airports=airports or [], related_airlines=airlines or [], related_routes=routes or [],
    )


# --- route matching ---------------------------------------------------


def test_article_matching_exact_route_scores_higher_than_no_route_match():
    movement = _movement()
    with_route = score_article(_article(routes=["BLR-DEL"]), movement)
    without_route = score_article(_article(routes=["BOM-MAA"]), movement)
    assert with_route.relevance_score > without_route.relevance_score
    assert "route" in with_route.matched_signals


def test_reverse_direction_route_still_matches():
    movement = _movement(origin="BLR", destination="DEL")
    match = score_article(_article(routes=["DEL-BLR"]), movement)
    assert "route" in match.matched_signals


# --- airport matching ---------------------------------------------------


def test_article_mentioning_both_airports_scores_higher_than_one():
    movement = _movement()
    both = score_article(_article(airports=["BLR", "DEL"]), movement)
    one = score_article(_article(airports=["DEL"]), movement)
    neither = score_article(_article(airports=["BOM"]), movement)
    assert both.relevance_score > one.relevance_score > neither.relevance_score
    assert "airport:origin" in both.matched_signals
    assert "airport:destination" in both.matched_signals


def test_unrelated_airport_only_does_not_get_airport_credit():
    movement = _movement()
    match = score_article(_article(airports=["BOM"]), movement)
    assert "airport:origin" not in match.matched_signals
    assert "airport:destination" not in match.matched_signals


# --- airline matching ---------------------------------------------------


def test_airline_operating_route_scores_higher_than_unrelated_airline():
    movement = _movement()
    known = score_article(_article(airlines=["IndiGo"]), movement, airlines_on_route=["IndiGo", "Air India"])
    unrelated = score_article(_article(airlines=["SpiceJet"]), movement, airlines_on_route=["IndiGo", "Air India"])
    assert known.relevance_score > unrelated.relevance_score
    assert "airline:operates_route" in known.matched_signals
    assert "airline:unrelated" in unrelated.matched_signals


def test_no_airlines_on_route_supplied_gives_mild_credit_for_any_airline():
    movement = _movement()
    match = score_article(_article(airlines=["IndiGo"]), movement, airlines_on_route=None)
    assert "airline:mentioned" in match.matched_signals


# --- date-window matching ---------------------------------------------------


def test_article_within_window_scores_higher_the_closer_it_is():
    movement = _movement()
    same_day = score_article(_article(days_offset=0), movement, date_window_days=10)
    near_edge = score_article(_article(days_offset=9), movement, date_window_days=10)
    assert same_day.relevance_score > near_edge.relevance_score


def test_article_outside_window_gets_no_date_proximity_signal():
    movement = _movement()
    outside = score_article(_article(days_offset=30), movement, date_window_days=10)
    assert "date_proximity" not in outside.matched_signals


def test_rank_articles_filters_out_of_window_candidates_via_min_relevance():
    movement = _movement()
    far_away = _article(days_offset=60, airports=[], airlines=[], routes=[], event_type="OTHER")
    config = MatchingConfig(date_window_days=10, min_relevance=0.35, top_n=5)
    ranked = rank_articles(movement, [far_away], config=config)
    assert ranked == []


# --- relevance ranking ---------------------------------------------------


def test_relevance_ranking_orders_best_match_first():
    movement = _movement()
    strong = _article(headline="Strong", airports=["BLR", "DEL"], routes=["BLR-DEL"], event_type="CAPACITY_REDUCTION")
    weak = _article(headline="Weak", days_offset=8, event_type="REGULATORY_CHANGE")
    config = MatchingConfig(date_window_days=10, min_relevance=0.0, top_n=5)
    ranked = rank_articles(movement, [weak, strong], config=config)
    assert ranked[0].article.headline == "Strong"


def test_rank_articles_respects_top_n():
    movement = _movement()
    articles = [_article(headline=f"Article {i}", airports=["BLR", "DEL"], routes=["BLR-DEL"]) for i in range(10)]
    config = MatchingConfig(date_window_days=10, min_relevance=0.0, top_n=3)
    ranked = rank_articles(movement, articles, config=config)
    assert len(ranked) == 3


def test_relevance_score_is_bounded_between_zero_and_one():
    movement = _movement()
    max_signal_article = _article(
        airports=["BLR", "DEL"], routes=["BLR-DEL"], airlines=["IndiGo"], event_type="CAPACITY_REDUCTION"
    )
    match = score_article(max_signal_article, movement, airlines_on_route=["IndiGo"])
    assert 0.0 <= match.relevance_score <= 1.0
