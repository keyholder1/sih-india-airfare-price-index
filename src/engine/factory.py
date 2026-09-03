"""
Factory functions for obtaining engine instances.

Returns the real implementations (real_adapters.py), wired against the
actual index_engine / data_quality / news-context modules. The stub
implementations (stubs.py) remain importable for tests/demos that want
guaranteed-synthetic, dependency-free output, but are no longer the
default -- no other file in the project needs to change to pick that up.
"""

from __future__ import annotations

from src.engine.protocols import (
    IndexEngineProtocol,
    DataQualityProtocol,
    RouteAnalyticsProtocol,
    NewsContextProtocol,
)
from src.engine.real_adapters import (
    RealIndexEngine,
    RealDataQualityEngine,
    RealRouteAnalyticsEngine,
    RealNewsContextEngine,
)


def get_index_engine() -> IndexEngineProtocol:
    """Return the active Index Engine implementation."""
    return RealIndexEngine()


def get_quality_engine() -> DataQualityProtocol:
    """Return the active Data Quality implementation."""
    return RealDataQualityEngine()


def get_route_analytics_engine() -> RouteAnalyticsProtocol:
    """Return the active Route Analytics implementation."""
    return RealRouteAnalyticsEngine()


def get_news_context_engine() -> NewsContextProtocol:
    """Return the active News/Context implementation."""
    return RealNewsContextEngine()
