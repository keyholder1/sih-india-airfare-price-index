"""
Factory functions for obtaining engine instances.

When the real Index Engine and sibling modules are ready, update
the functions below to return the real implementations instead of
the stubs.  No other file in the project needs to change.
"""

from __future__ import annotations

from src.engine.protocols import (
    IndexEngineProtocol,
    DataQualityProtocol,
    RouteAnalyticsProtocol,
    NewsContextProtocol,
)
from src.engine.stubs import (
    StubIndexEngine,
    StubDataQualityEngine,
    StubRouteAnalyticsEngine,
    StubNewsContextEngine,
)


def get_index_engine() -> IndexEngineProtocol:
    """Return the active Index Engine implementation."""
    # TODO: Replace with real engine when available
    # from index_engine import AirfarePriceIndex
    # return AirfarePriceIndex()
    return StubIndexEngine()


def get_quality_engine() -> DataQualityProtocol:
    """Return the active Data Quality implementation."""
    # TODO: Replace with real engine when available
    return StubDataQualityEngine()


def get_route_analytics_engine() -> RouteAnalyticsProtocol:
    """Return the active Route Analytics implementation."""
    # TODO: Replace with real engine when available
    return StubRouteAnalyticsEngine()


def get_news_context_engine() -> NewsContextProtocol:
    """Return the active News/Context implementation."""
    # TODO: Replace with real engine when available
    return StubNewsContextEngine()
