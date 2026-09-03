"""
Route sub-package. Collects all route routers for mounting in main.
"""

from api.routes.index import router as index_router
from api.routes.routes import router as routes_router
from api.routes.quality import router as quality_router
from api.routes.news import router as news_router
from api.routes.analytics import router as analytics_router
from api.routes.dashboard import router as dashboard_router

__all__ = [
    "index_router",
    "routes_router",
    "quality_router",
    "news_router",
    "analytics_router",
    "dashboard_router",
]
