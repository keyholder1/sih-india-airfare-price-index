# News & Event Context Layer

**Status: SIH prototype.** This document describes the `news_context`
module and the modules it depends on (`news_models`, `news_provider`,
`mock_news_provider`, `news_matching`, `context_signals`). It answers a
single question:

> "Why did airfare prices move?"

It never answers that question with certainty, and it never changes the
index. See [Statistical distinction](#statistical-distinction-never-causal)
below before wiring this into any user-facing text.

---

## 1. Where this sits in the pipeline

```
clean fare data
  -> AirfarePriceIndex          (src/index_engine/index.py — FROZEN, unchanged)
  -> route price movement       (RouteInflationRow, src/index_engine/route_analysis.py)
  -> significant movement?      (news_context.is_significant_movement)
  -> News & Event Context layer (this module)
  -> relevant articles/events
  -> dashboard
```

This module is a **pure consumer** of index-engine output. It imports
`RouteInflationRow` to read a route's already-computed `mom`/`yoy`
percentage change; it does not import, call, or modify anything in
`index.py`, `aggregation.py`, `weighting.py`, `contribution.py`, or any
other file that produces an index number. Nothing in `index_engine`'s
core modules imports anything from this layer either — the dependency is
one-directional, so the 88-test-and-growing Index Engine test suite runs
identically whether or not this module exists.

The eventual shape (only `news_context` exists today; the rest is future
work described in §6):

```
Airfare Index
  -> Why Did Fares Move?
       +-------+---------+----------+---------------+
       | News  | Weather | Capacity | Cancellations |
       +-------+---------+----------+---------------+
```

## 2. Data model

`news_models.py` defines the shapes:

- **`NewsArticle`** — `headline`, `source`, `published_at`, `url` (the
  *original* publisher link — required, never empty), `event_type`,
  optional `summary`/snippet, `related_airlines`, `related_airports`,
  `related_routes`, optional `confidence_score`, and `is_mock` (always
  `True` for anything from `MockNewsProvider`).
- **`RouteMovement`** — the input: a route, its `change_pct`, which metric
  (`mom`/`yoy`), the period, and the timestamp to search around. Built
  from a `RouteInflationRow` via `route_movement_from_row`, never
  recomputed.
- **`NewsMatch`** — one `NewsArticle` plus its `relevance_score` and the
  list of signals that fired (`matched_signals`), so a reviewer can see
  *why* an article was surfaced.
- **`NewsContextResult`** — a `RouteMovement`, its ranked `matches`, the
  deduplicated `potential_factors` (event types across the matches), and a
  standing `disclaimer` string.

Event types (`EventType`, a closed set of ten string literals):
`FLIGHT_CANCELLATION`, `CAPACITY_REDUCTION`, `WEATHER_DISRUPTION`,
`AIRPORT_DISRUPTION`, `AIRLINE_OPERATIONAL_ISSUE`, `STRIKE`,
`REGULATORY_CHANGE`, `FUEL_PRICE_CHANGE`, `GEOPOLITICAL_EVENT`, `OTHER`.

## 3. Provider interface — connecting a real news API

`news_provider.NewsProvider` is the only seam a teammate needs to fill in:

```python
class NewsProvider(ABC):
    @abstractmethod
    def search(self, query: NewsSearchQuery) -> List[NewsArticle]: ...
```

To connect a real API (NewsAPI.org, GNews, a licensed wire feed, an
internal scraper): subclass `NewsProvider`, call the real API inside
`search`, and map each result into a `NewsArticle` with `is_mock=False`
and `url` set to the real article's canonical link. Nothing else in this
package needs to change — `NewsContextService` only ever talks to the
abstract interface.

`mock_news_provider.MockNewsProvider` is the only concrete provider
shipped today. Its `DEMO_ARTICLES` are **entirely fabricated** — headlines
are prefixed `[MOCK]`, every article has `is_mock=True`, and none of it
should ever be shown to a user as if it were real reporting. It exists so
the matching logic and dashboard formatting have something to run against
in tests and in the SIH demo before a real API key is available.

## 4. Relevance matching

`news_matching.score_article(article, movement, ...)` combines six
bounded `[0, 1]` signals into one weighted `relevance_score`:

| Signal | Weight | What it checks |
|---|---|---|
| Date proximity | 0.25 | Linear decay from the movement's `as_of` date to 0 at the edge of `date_window_days` |
| Airport mention | 0.25 | Half credit for the origin OR destination airport named, full credit for both |
| Route mention | 0.15 | The article explicitly tags the route (either direction) |
| Airline mention | 0.15 | Full credit if the named airline is known to operate the route (`airlines_on_route`), partial credit otherwise |
| Event type | 0.10 | Higher for event types that plausibly move fares (capacity, cancellations, strikes, disruptions), zero for `OTHER` |
| Geographic relevance | 0.10 | Full credit if it names this route's airports; half credit if it names no specific airport (e.g. a national fuel-price story); zero if it names airports unrelated to this route |

`rank_articles(...)` scores every candidate, drops anything below
`min_relevance` (default `0.35`), and returns the top `top_n` (default 5),
most-relevant first, ties broken by more recent publication.

This is a transparent heuristic, not a trained model — every weight is a
named constant in `news_matching.py` and can be re-tuned without touching
the scoring function's structure.

## 5. Statistical distinction: never causal

The disclaimer baked into every `NewsContextResult`
(`news_models.CAUSATION_DISCLAIMER`) and repeated in both dashboard
renderers says explicitly that matched articles are **contextual
evidence, not a confirmed cause**. Any text generated from this layer
must say:

- "Airfare increase **coincided with**..."
- "**Potential related factors**..."
- "**Relevant events detected** around this period..."

and must never say "News X **caused** the airfare increase." A high
`relevance_score` means an article overlaps in date/airport/airline/route
with the movement — it is not evidence of a causal mechanism, and this
module has no way to establish one.

## 6. Original article links

`NewsArticle.url` is required and validated non-empty
(`NewsArticle.__post_init__`). It is passed through unchanged by
`news_matching`, `NewsContextService`, and both dashboard formatters
(`to_dashboard_dict`, `to_dashboard_text`) — nothing in this layer stores,
serves, or renders full article bodies, only the `summary`/snippet a
provider supplies. A dashboard's "Read original article" link must use
this `url` directly, e.g.:

```json
{
  "headline": "...",
  "source": "Reuters",
  "published_at": "2026-08-14T09:00:00",
  "url": "https://original-publisher.com/article/...",
  "event_type": "AIRLINE_OPERATIONAL_ISSUE",
  "relevance_score": 0.91
}
```

## 7. Using it

```python
from index_engine import (
    AirfareAnalytics, MockNewsProvider, NewsContextService, NewsContextConfig,
    attach_news_context, to_dashboard_text,
)

analytics = AirfareAnalytics(base_period="2026-01").calculate(fares_df, current_period="2026-08")

service = NewsContextService(MockNewsProvider(), config=NewsContextConfig(significance_threshold_pct=5.0))
context_by_route = attach_news_context(
    analytics.route_inflation, period="2026-08", service=service,
)

for route, context in context_by_route.items():
    print(to_dashboard_text(context))
```

`to_dashboard_text` defaults to `ascii_only=True`, rendering event-type
markers as `[LABEL]` instead of emoji — safe to `print()` on any console,
including a stock Windows terminal (`cp1252`/`cp437` stdout), which raises
`UnicodeEncodeError` on most of the emoji otherwise. Pass
`to_dashboard_text(context, ascii_only=False)` only when the output target
is known to be UTF-8. A real web dashboard should render straight from
`to_dashboard_dict(context)` (which always includes the `emoji` field)
rather than parsing this string either way.

`attach_news_context` only calls the provider for routes whose `mom`/`yoy`
change already exceeds `significance_threshold_pct` — routine noise never
triggers a news search. Swap `MockNewsProvider()` for a real
`NewsProvider` subclass and nothing else in the call above changes.

## 8. Future external signals

`context_signals.py` defines the generic interface future signals should
implement: `ContextSignalProvider.get_signal(movement) -> ContextSignalResult`.
`news_context.NewsContextSignalAdapter` is the first (and, today, only)
implementation, wrapping `NewsContextService`. Weather, airline capacity,
cancellation-rate, and ATF/fuel-price signals are expected to become
sibling `ContextSignalProvider` implementations later, combined via
`combine_context_signals(movement, providers)` into one "why did fares
move" view — without any of them touching `index_engine.index` or each
other.

## 9. Limitations

- **Heuristic, not learned.** The relevance score is a fixed weighted sum
  of simple text/metadata overlaps. It will miss articles that are
  genuinely relevant but don't share an exact airport code, airline name,
  or route tag, and can surface articles that overlap coincidentally.
- **No real news source yet.** `MockNewsProvider` is fabricated demo data
  only. Every real deployment must connect a real `NewsProvider` before
  this layer's output can be shown to end users as if it were real news.
- **No causal inference.** See §5 — this layer cannot and does not
  determine whether an event actually caused a fare movement, only that
  the two coincided by date/route/airport/airline/event-type.
- **English-language, India-domestic-route bias.** The generic keyword
  list and airport/city alias table are tuned for Indian domestic routes;
  a broader deployment would need a larger alias table and likely
  multilingual query support.
- **No deduplication across near-identical articles** from different
  outlets covering the same event — each is scored and shown
  independently.
