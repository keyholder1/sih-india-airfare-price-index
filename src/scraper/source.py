"""``FareSource`` — the provider interface every collection source
implements (an airline's own site, an OTA, a real flight-data API, or the
mock generator). ``scraper.runner`` only ever talks to this interface, the
same way ``index_engine.news_context`` only ever talks to ``NewsProvider``
— a new source is a new subclass, nothing else in this package changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .models import SourceCallResult


@dataclass
class SearchRequest:
    """One route/date fare search. ``booking_date`` is supplied by the
    caller (usually "today") — booking horizon is always derived as
    ``(flight_date - booking_date).days``, never asked of the source."""

    origin: str
    destination: str
    flight_date: date
    booking_date: date
    passengers: int = 1
    cabin: Optional[str] = None
    fare_type: Optional[str] = None

    def __post_init__(self) -> None:
        if self.booking_date > self.flight_date:
            raise ValueError("booking_date must be on or before flight_date")

    @property
    def booking_horizon_days(self) -> int:
        return (self.flight_date - self.booking_date).days


class FareSource(ABC):
    """A single place fares can come from."""

    name: str

    @abstractmethod
    def search_fares(self, request: SearchRequest) -> SourceCallResult:
        """Return every fare this source has for ``request``.

        Implementations must never raise for an ordinary "no data"/"site
        blocked us"/"request failed" outcome — encode that as a
        ``SourceCallResult.status`` instead, so ``scraper.runner`` can
        record it in the run report rather than the whole run crashing.
        Raising is reserved for genuine programming errors.
        """
        raise NotImplementedError
