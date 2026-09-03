"""Generic "context signal" interface.

News is the first of several planned explanatory signals for "why did fares
move" (see docs/news_context.md / project README roadmap):

    Airfare Index -> route movement -> Why Did Fares Move?
                                            |
              +------------+------------+------------+
              |    News    |  Weather   |  Capacity  |  Cancellations  ...
              +------------+------------+------------+

Every signal answers the same question about the same input (a
``RouteMovement``) and returns the same shape of answer (a
``ContextSignalResult``), so a future aggregator can loop over an arbitrary
list of signal providers without knowing anything provider-specific. None
of these signals may write back to the index — see the module docstring on
:mod:`news_context` for why.

This module intentionally defines *only* the interface, not a concrete
weather/capacity/cancellation implementation — those are future work.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List

from .news_models import RouteMovement


@dataclass
class ContextSignalResult:
    """What any context signal (news, weather, capacity, cancellations...)
    reports back for one route movement. ``items`` is intentionally a list
    of plain dicts — each signal defines its own item shape (a news
    article, a weather event, a capacity-cut record...); the aggregator
    only needs ``signal_name`` and ``summary`` to build a combined view.
    """

    signal_name: str
    items: List[dict] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {"signal_name": self.signal_name, "items": self.items, "summary": self.summary}


class ContextSignalProvider(ABC):
    """Something that can explain a route's price movement from one angle.

    ``NewsContextSignalAdapter`` (in :mod:`news_context`) is the first
    implementation. A future ``WeatherSignalProvider``,
    ``CapacitySignalProvider``, or ``CancellationSignalProvider`` would
    implement this same interface and slot into
    :func:`combine_context_signals` unchanged.
    """

    @abstractmethod
    def get_signal(self, movement: RouteMovement) -> ContextSignalResult:
        raise NotImplementedError


def combine_context_signals(
    movement: RouteMovement, providers: List[ContextSignalProvider]
) -> Dict[str, ContextSignalResult]:
    """Run every provider for one route movement and key the results by
    signal name. Providers are independent — one raising or returning empty
    never affects another, and none of them can alter ``movement`` itself
    (it is read, never written)."""
    results = [p.get_signal(movement) for p in providers]
    return {r.signal_name: r for r in results}
