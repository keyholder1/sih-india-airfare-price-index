"""
Engine interfaces and stub implementations.

This package defines the Protocol interfaces that the real Index Engine
and sibling modules must satisfy, along with stub implementations that
return clearly-labeled synthetic data for development.
"""

from src.engine.protocols import (
    IndexEngineProtocol,
    DataQualityProtocol,
    RouteAnalyticsProtocol,
    NewsContextProtocol,
    IndexResult,
    RouteIndex,
    TimeseriesPoint,
    QualityReport,
    RouteHealth,
    SourceHealth,
    RouteAnalysis,
    RouteContext,
    NewsEvent,
)
from src.engine.stubs import (
    StubIndexEngine,
    StubDataQualityEngine,
    StubRouteAnalyticsEngine,
    StubNewsContextEngine,
)
from src.engine.factory import (
    get_index_engine,
    get_quality_engine,
    get_route_analytics_engine,
    get_news_context_engine,
)

__all__ = [
    # Protocols
    "IndexEngineProtocol",
    "DataQualityProtocol",
    "RouteAnalyticsProtocol",
    "NewsContextProtocol",
    # Result types
    "IndexResult",
    "RouteIndex",
    "TimeseriesPoint",
    "QualityReport",
    "RouteHealth",
    "SourceHealth",
    "RouteAnalysis",
    "RouteContext",
    "NewsEvent",
    # Stubs
    "StubIndexEngine",
    "StubDataQualityEngine",
    "StubRouteAnalyticsEngine",
    "StubNewsContextEngine",
    # Factories
    "get_index_engine",
    "get_quality_engine",
    "get_route_analytics_engine",
    "get_news_context_engine",
]
