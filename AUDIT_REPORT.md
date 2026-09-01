# Audit Report: `sih-backend` vs. Upstream Pull Requests

**Date**: September 1, 2026  
**Audited Repository**: `sih-backend`  
**Target Repository**: `keyholder1/sih-india-airfare-price-index` (PR #1, PR #2, PR #3)  
**Status**: Completed (Read-only comparison & verification)

---

## 1. File Inventory of `sih-backend`

Below is the verified inventory of all source and test files on disk in `sih-backend/`:

| File Path | Description |
|---|---|
| `.env.example` | Example environment variables template (`API_KEY`, `FRONTEND_ORIGIN`). |
| `README.md` | Project architecture, quickstart, API documentation, and stub swapping instructions. |
| `requirements.txt` | Core backend dependencies (`fastapi`, `uvicorn`, `pydantic`, `httpx`, `pytest`, etc.). |
| `api/__init__.py` | Package initialization for API layer. |
| `api/main.py` | FastAPI app instance, CORS configuration, `/health` route, and versioned `/api/v1` router mount. |
| `api/dependencies.py` | API key authentication dependency (`verify_api_key`) validating `X-API-Key`. |
| `api/schemas.py` | Pydantic request and response models across all endpoints with OpenAPI field descriptions. |
| `api/routes/__init__.py` | Router exports for index, routes, quality, news, analytics, and dashboard. |
| `api/routes/analytics.py` | Placeholder router for future analytics endpoints (`/volatility`, `/trends`, `/seasonal`). |
| `api/routes/dashboard.py` | Router exposing `GET /api/v1/dashboard/summary`. |
| `api/routes/index.py` | Router exposing `POST /api/v1/index/calculate` and `GET /api/v1/index/timeseries`. |
| `api/routes/news.py` | Router exposing `GET /api/v1/routes/{route}/context`. |
| `api/routes/quality.py` | Router exposing `GET /api/v1/quality`. |
| `api/routes/routes.py` | Router exposing `GET /api/v1/routes`. |
| `api/services/__init__.py` | Package initialization for service adapter modules. |
| `api/services/dashboard_service.py` | Aggregates index, route analytics, data quality, and alert data into a single dashboard payload. |
| `api/services/index_service.py` | Adapts index calculation and timeseries requests between Pydantic and `IndexEngineProtocol`. |
| `api/services/news_service.py` | Adapts route news context requests to `NewsContextProtocol`. |
| `api/services/quality_service.py` | Adapts quality reporting requests to `DataQualityProtocol`. |
| `api/services/route_service.py` | Adapts route listing requests to `RouteAnalyticsProtocol`. |
| `src/__init__.py` | Package initialization for top-level `src`. |
| `src/engine/__init__.py` | Package exports for engine protocols, stubs, and factory accessors. |
| `src/engine/factory.py` | Dependency injection factory providing instances of index, quality, route, and news engines. |
| `src/engine/protocols.py` | `typing.Protocol` interfaces and dataclasses defining the expected contract for all engines. |
| `src/engine/stubs.py` | Stub implementations providing synthetic test data for all engine protocols. |
| `tests/conftest.py` | Pytest fixtures (test client, valid API key headers, test observation data). |
| `tests/test_auth.py` | Auth tests for missing/invalid API keys, public `/health`, and route protection. |
| `tests/test_dashboard.py` | Tests for dashboard summary structure, movers, contributors, and quality integration. |
| `tests/test_index.py` | Tests for `/api/v1/index/calculate` validation, edge cases, and synthetic responses. |
| `tests/test_news.py` | Tests for `/api/v1/routes/{route}/context` status codes, event shapes, and 404s. |
| `tests/test_quality.py` | Tests for `/api/v1/quality` report structures, score ranges, and health breakdowns. |
| `tests/test_routes.py` | Tests for `/api/v1/routes` list response, weights, and status fields. |
| `tests/test_schemas.py` | Unit tests verifying Pydantic serialization/deserialization across all models. |
| `tests/test_timeseries.py` | Tests for `/api/v1/index/timeseries` date range validation and pagination. |

---

## 2. Stub Inventory & Placeholder Markers

The stubs in `sih-backend` are organized in `src/engine/stubs.py` and instantiated in `src/engine/factory.py`:

| Stub Class | Location | Factory Function | Interfaces / Stood-In Module | Output Label |
|---|---|---|---|---|
| `StubIndexEngine` | `src/engine/stubs.py:40` | `get_index_engine()` (`factory.py:25`) | `IndexEngineProtocol` standing in for statistical calculation engine (`AirfarePriceIndex`). | Returns `data_source="synthetic"`, `flags=["stub_data"]` |
| `StubDataQualityEngine` | `src/engine/stubs.py:130` | `get_quality_engine()` (`factory.py:33`) | `DataQualityProtocol` standing in for the Data Quality validator (`validate_fare_batch`). | Returns `data_source="synthetic"` |
| `StubRouteAnalyticsEngine` | `src/engine/stubs.py:191` | `get_route_analytics_engine()` (`factory.py:39`) | `RouteAnalyticsProtocol` standing in for route analysis and traffic weighting module. | Returns `data_source="synthetic"` |
| `StubNewsContextEngine` | `src/engine/stubs.py:210` | `get_news_context_engine()` (`factory.py:45`) | `NewsContextProtocol` standing in for route news/event correlation module (`NewsContextService`). | Returns `data_source="synthetic"` |

### Placeholder Markers / TODOs
- `src/engine/factory.py:27`: `# TODO: Replace with real engine when available`
- `src/engine/factory.py:35`: `# TODO: Replace with real engine when available`
- `src/engine/factory.py:41`: `# TODO: Replace with real engine when available`
- `src/engine/factory.py:47`: `# TODO: Replace with real engine when available`
- `api/routes/analytics.py:1-19`: Empty router with comment markers `# Future endpoints: /volatility, /trends, /seasonal`.

---

## 3. Current Endpoint Inventory

| HTTP Method | Path | Summary / Description | Auth Required | Current Data Provenance |
|---|---|---|---|---|
| `GET` | `/health` | Server health check (`{"status": "ok"}`) | **No** | **Real** (System status) |
| `POST` | `/api/v1/index/calculate` | Composite airfare price index computation | **Yes** (`X-API-Key`) | **Synthetic** (`data_source: "synthetic"`) |
| `GET` | `/api/v1/index/timeseries` | Historical index time series with pagination | **Yes** (`X-API-Key`) | **Synthetic** (`data_source: "synthetic"`) |
| `GET` | `/api/v1/routes` | Route-level index and coverage analysis | **Yes** (`X-API-Key`) | **Synthetic** (`data_source: "synthetic"`) |
| `GET` | `/api/v1/quality` | Ingestion data quality health assessment | **Yes** (`X-API-Key`) | **Synthetic** (`data_source: "synthetic"`) |
| `GET` | `/api/v1/routes/{route}/context` | News/event context for route fare movement | **Yes** (`X-API-Key`) | **Synthetic** (`data_source: "synthetic"`) |
| `GET` | `/api/v1/dashboard/summary` | Aggregated dashboard overview metrics | **Yes** (`X-API-Key`) | **Synthetic** (`data_source: "synthetic"`) |

---

## 4. Test Suite Execution Results

Running pytest against `sih-backend`:
- **Command**: `.venv\Scripts\pytest tests -v`
- **Total Collected**: 62 tests
- **Passed**: **62**
- **Failed**: **0**
- **Errors**: **0**
- **Warnings**: 1 (`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead`)
- **Execution Time**: ~1.00s

---

## 5. Upstream Pull Requests Review

### PR #1 — Airfare Price Index Engine & Analytics
- **URL**: https://github.com/keyholder1/sih-india-airfare-price-index/pull/1
- **Status**: **Open**
- **Branch**: `index-engine` targeting `main`
- **Commit**: `5d37f66c4c23dae6e35ee058598ec99220649d48` (1 commit)
- **CI / Review Status**: No failing CI checks. CodeRabbit automated bot posted an info note. 88 unit tests passing in the PR branch.
- **Actual Modules Implemented**:
  1. `AirfarePriceIndex` (`src/index_engine/index.py`): Core statistical index calculation, representative fares (median/trimmed mean), outlier filtering (IQR/MAD/percentile), MoM/YoY changes, and exact Laspeyres/arithmetic/geometric aggregation.
  2. `AirfareAnalytics` (`src/index_engine/analytics.py`): Unified analytics combining price index, volatility, route-level inflation heatmap, top rankings, geographic route mapping, and affordability.
  3. `Volatility` (`src/index_engine/volatility.py`): Fare dispersion, CV, and price volatility by route and period.
  4. `Route Selection & Traffic` (`src/index_engine/route_selection.py`, `traffic.py`, `city_mapping.py`): DGCA domestic passenger traffic weight generator (2,228 real routes) and scraper priority tiering.
  5. `Affordability` (`src/index_engine/affordability.py`): Relative airfare affordability index vs. income series.
  6. Standalone Prototype API (`api/main.py`, `api/schemas.py`): Minimal unauthenticated FastAPI prototype included in the PR for basic engine testing.

#### Real Public Interface of PR #1
- **`AirfarePriceIndex`**:
  ```python
  class AirfarePriceIndex:
      def __init__(
          self,
          base_period: str,
          weights: Optional[pd.DataFrame] = None,
          config: Optional[IndexConfig] = None,
      ) -> None: ...

      def calculate(
          self,
          observations: Union[pd.DataFrame, Sequence[dict]],
          current_period: str,
      ) -> IndexResult: ...
  ```
- **`IndexResult` Dataclass**:
  - Fields: `base_period: str`, `current_period: str`, `national_index: Optional[float]`, `mom_change_pct: Optional[float]`, `yoy_change_pct: Optional[float]`, `routes_covered: int`, `routes_total: int`, `observations_used: int`, `coverage_rate: float`, `representative_method: str`, `aggregation_method: str`, `route_indices: List[RouteIndexResult]`, `route_contributions: List[RouteContribution]`, `quality_flags: List[str]`, `cleaning_report: CleaningReport`, `observations_received: int`, `observations_rejected: int`, `outliers_flagged: int`, `routes_expected: int`, `routes_with_data: int`.
  - Methods: `to_dict() -> dict`.
- **`RouteIndexResult` Dataclass**:
  - Fields: `route: str`, `origin: str`, `destination: str`, `period: str`, `base_period_fare: Optional[float]`, `period_fare: Optional[float]`, `route_index: Optional[float]`, `observations_used: int`, `weight_raw: Optional[float]`, `weight_normalized: Optional[float]`, `status: str`.
- **`RouteContribution` Dataclass**:
  - Fields: `route: str`, `weight_normalized: float`, `route_index_current: Optional[float]`, `route_index_previous: Optional[float]`, `contribution_points: Optional[float]`.
- **`AirfareAnalytics`**:
  ```python
  class AirfareAnalytics:
      def __init__(
          self,
          base_period: str,
          weights: Optional[pd.DataFrame] = None,
          config: Optional[IndexConfig] = None,
          volatility_config: Optional[VolatilityConfig] = None,
          traffic_weight_coverage: Optional[float] = None,
      ) -> None: ...

      def calculate(
          self,
          observations: Union[pd.DataFrame, list],
          current_period: str,
          income_series: Optional[pd.DataFrame] = None,
          income_indicator: str = "income_index",
      ) -> AnalyticsResult: ...
  ```

---

### PR #2 — Data Quality Validation Layer
- **URL**: https://github.com/keyholder1/sih-india-airfare-price-index/pull/2
- **Status**: **Open**
- **Branch**: `feature/data-quality-validation` targeting `index-engine` (stacked on PR #1)
- **Commit**: `a2e71eb85b5641fa5ceaa77addde507dddd70c83` (1 commit)
- **CI / Review Status**: No failing CI checks. CodeRabbit automated bot posted an info note. 141 tests passing (88 PR #1 tests + 52 quality tests + 1 integration test).
- **Actual Modules Implemented**:
  1. `validate_fare_batch` (`src/data_quality/pipeline.py`): Full validation pipeline sitting between scraper/DB and index engine.
  2. Field validation (`src/data_quality/validation.py`): Required columns, non-positive fares, date formats, non-INR currencies.
  3. Duplicate detection (`src/data_quality/duplicates.py`): Exact duplicates (rejected) vs. potential duplicates (flagged).
  4. Reason codes (`src/data_quality/reason_codes.py`): Standardized rejection/flag reasons and health statuses (`HEALTHY`, `DEGRADED`, `FAILED`, `UNKNOWN`).
  5. Health & completeness scoring (`src/data_quality/health.py`, `completeness.py`, `scoring.py`): Route health, source health, completeness rate, quality score (0–100), and letter grade (`A`, `B`, `C`, `D`, `F`).

#### Real Public Interface of PR #2
- **`validate_fare_batch`**:
  ```python
  def validate_fare_batch(
      raw_data: Union[pd.DataFrame, Sequence[dict]],
      route_attempts: Optional[RouteAttempts] = None,
      config: Optional[DataQualityConfig] = None,
      reference_time: Optional[pd.Timestamp] = None,
      base_period: Optional[str] = None,
      current_period: Optional[str] = None,
  ) -> DataQualityResult: ...
  ```
- **`DataQualityResult` Dataclass**:
  - Fields: `records_received: int`, `records_valid: int`, `records_flagged: int`, `records_rejected: int`, `completeness_rate: float`, `validity_rate: float`, `duplicate_rate: float`, `quality_score: float` (0–100 scale), `quality_grade: str` ("A".."F"), `rejection_reasons: Dict[str, int]`, `flag_reasons: Dict[str, int]`, `duplicate_count: int`, `exact_duplicate_count: int`, `potential_duplicate_count: int`, `completeness: CompletenessReport`, `source_health: List[SourceHealth]`, `route_health: List[RouteHealth]`, `valid_observations: List[Dict[str, Any]]`, `overall_route_success_rate: Optional[float]`, `overall_route_coverage: Optional[float]`, `record_results: List[Dict[str, Any]]`.
  - Methods: `to_dict(include_records: bool = False) -> dict`.
- **`SourceHealth` Dataclass**:
  - Fields: `source: str`, `status: str`, `observations_received: int`, `valid_observations: int`, `flagged_observations: int`, `rejected_observations: int`, `observation_validity_rate: float`, `routes_requested: Optional[int]`, `routes_successful: Optional[int]`, `routes_failed: Optional[int]`, `route_success_rate: Optional[float]`, `oldest_observation: Optional[str]`, `newest_observation: Optional[str]`, `data_age_seconds: Optional[float]`.
- **`RouteHealth` Dataclass**:
  - Fields: `route: str`, `origin: str`, `destination: str`, `observations_total: int`, `observations_valid: int`, `observations_rejected: int`, `route_quality_rate: float`, `data_completeness: float`, `has_base_period_data: Optional[bool]`, `has_current_period_data: Optional[bool]`.

---

### PR #3 — News & Event Context Module
- **URL**: https://github.com/keyholder1/sih-india-airfare-price-index/pull/3
- **Status**: **Open**
- **Branch**: `feature/news-event-context` targeting `feature/data-quality-validation` (stacked on PR #2)
- **Commit**: `8ccac9b22848340a117ed72827fa573796478989` (1 commit)
- **CI / Review Status**: No failing CI checks. CodeRabbit automated bot posted an info note. 169 tests passing (141 existing + 28 news tests).
- **Actual Modules Implemented**:
  1. `NewsContextService` (`src/index_engine/news_context.py`): Correlates route fare movements with relevant news and events.
  2. Multi-signal matching (`src/index_engine/news_matching.py`): Matches candidate articles using 6 scoring signals (date proximity, airport mention, route mention, airline mention, event type, and geographic relevance).
  3. Controlled event taxonomy (`src/index_engine/news_models.py`): Standard event types (`FLIGHT_CANCELLATION`, `CAPACITY_REDUCTION`, `WEATHER_DISRUPTION`, `AIRPORT_DISRUPTION`, `AIRLINE_OPERATIONAL_ISSUE`, `STRIKE`, `REGULATORY_CHANGE`, `FUEL_PRICE_CHANGE`, `GEOPOLITICAL_EVENT`, `OTHER`).
  4. Provider seam (`src/index_engine/news_provider.py`, `mock_news_provider.py`): Abstract `NewsProvider` class and `MockNewsProvider` with mock dataset (`is_mock=True`).
  5. Dashboard renderers (`src/index_engine/news_context.py`): `to_dashboard_dict(result)` and `to_dashboard_text(result)`.

#### Real Public Interface of PR #3
- **`NewsContextService`**:
  ```python
  class NewsContextService:
      def __init__(
          self,
          provider: NewsProvider,
          config: Optional[NewsContextConfig] = None,
      ) -> None: ...

      def get_context(
          self,
          movement: RouteMovement,
          airlines_on_route: Optional[Iterable[str]] = None,
      ) -> NewsContextResult: ...

      def get_context_for_row(
          self,
          row: RouteInflationRow,
          period: Optional[str] = None,
          as_of: Optional[datetime] = None,
          metric: Literal["mom", "yoy"] = "mom",
          airlines_on_route: Optional[Iterable[str]] = None,
      ) -> Optional[NewsContextResult]: ...
  ```
- **`RouteMovement` Dataclass**:
  - Fields: `route: str`, `origin: str`, `destination: str`, `change_pct: float`, `metric: Literal["mom", "yoy"]`, `period: str`, `as_of: datetime`.
  - Properties: `direction -> "increase" | "decrease"`.
- **`NewsArticle` Dataclass**:
  - Fields: `headline: str`, `source: str`, `published_at: datetime`, `url: str`, `event_type: EventType`, `summary: Optional[str]`, `related_airlines: List[str]`, `related_airports: List[str]`, `related_routes: List[str]`, `confidence_score: Optional[float]`, `is_mock: bool`.
- **`NewsMatch` Dataclass**:
  - Fields: `article: NewsArticle`, `relevance_score: float`, `matched_signals: List[str]`.
- **`NewsContextResult` Dataclass**:
  - Fields: `movement: RouteMovement`, `matches: List[NewsMatch]`, `potential_factors: List[EventType]`, `disclaimer: str`.
- **Dashboard Helper**:
  - `to_dashboard_dict(result: NewsContextResult) -> dict` returning keys: `route`, `origin`, `destination`, `change_pct`, `direction`, `metric`, `period`, `potential_related_factors` (list of `{event_type, label, emoji}`), `related_news` (list of article dicts with publisher `url`), `disclaimer`.

---

## 6. Interface & Contract Mismatches

| Module / PR | Expected Contract in `sih-backend` (`protocols.py`) | Actual Real Contract in PR | Concrete Mismatches Found |
|---|---|---|---|
| **PR #1 (Index Engine)** | `IndexEngineProtocol.calculate_index(observations, base_period, current_period, config)` returning `IndexResult` | `AirfarePriceIndex(base_period, weights, config).calculate(observations, current_period)` returning `IndexResult` | **1. Instantiation vs. Method Arguments**: Base period and weights are passed to `__init__`, not `calculate`.<br>**2. Method Name**: `calculate()` vs. `calculate_index()`.<br>**3. Observation Schema**: Real engine expects standardized columns (`observation_id`, `airline`, `origin`, `destination`, `flight_date`, `booking_date`, `total_fare`, `currency`), while backend's `ObservationInput` schema currently accepts `route`, `fare`, `date`, `source`.<br>**4. Result Field Names**: Real engine outputs `mom_change_pct`, `yoy_change_pct`, `quality_flags`, `cleaning_report` vs. stub's `mom`, `yoy`, `flags`, `quality_score`.<br>**5. Timeseries Method**: Real engine computes single periods or uses batch timeseries calculation; it does not have a single `get_timeseries(start_date, end_date)` method built into the core engine class (the PR wrapper loops `engine.calculate`). |
| **PR #1 (Route Analytics)** | `RouteAnalyticsProtocol.get_route_analysis()` returning `list[RouteAnalysis]` | `AirfareAnalytics(base_period, ...).calculate(observations, current_period)` returning `AnalyticsResult` | **1. Class & Method**: `AirfareAnalytics.calculate()` requires `observations` and `current_period`; no standalone zero-argument `get_route_analysis()` method.<br>**2. Result Shape**: Real module returns `RouteInflationRow` objects inside `AnalyticsResult.route_inflation` containing `base_fare`, `current_fare`, `mom_inflation_pct`, `yoy_inflation_pct`, `contribution_points`, `volatility`, etc. |
| **PR #2 (Data Quality)** | `DataQualityProtocol.assess_quality(observations)` returning `QualityReport` | `validate_fare_batch(raw_data, route_attempts, config, ...)` returning `DataQualityResult` | **1. Function vs. Class**: PR #2 is a functional pipeline (`validate_fare_batch`), not an engine class with `assess_quality()`.<br>**2. Score Scale**: Real quality score is `0.0–100.0` with `quality_grade` ("A"–"F"), whereas backend stub assumed a `0.0–1.0` float.<br>**3. Health Models**: `SourceHealth` and `RouteHealth` have different field names (`observations_total`, `observations_valid`, `route_quality_rate`, `data_completeness` vs. stub's `valid`, `rejected`, `health_score`, `reliability_score`). |
| **PR #3 (News Context)** | `NewsContextProtocol.async def get_route_context(route_code: str) -> RouteContext` | `NewsContextService(provider).get_context(movement: RouteMovement) -> NewsContextResult` or `get_context_for_row(row)` | **1. Synchronous vs. Asynchronous**: Real `NewsContextService` is synchronous (providers implement sync `search()`), whereas backend protocol defined `async def get_route_context()`.<br>**2. Input Signature**: Real service requires a `RouteMovement` object (`route`, `origin`, `destination`, `change_pct`, `period`, `as_of`), not just a bare `route_code` string.<br>**3. Output Structure**: Real result wraps `matches: List[NewsMatch]` (with `article: NewsArticle`, `relevance_score`, `matched_signals`) and `potential_factors: List[EventType]` rather than a flat `events: list[NewsEvent]`. |

---

## 7. Required Changes in `sih-backend` for Integration

### To Integrate PR #1 (`index_engine`)
1. `src/engine/protocols.py`:
   - Update `IndexEngineProtocol` and `RouteAnalyticsProtocol` signatures to reflect `AirfarePriceIndex` and `AirfareAnalytics` lifecycle (`__init__` configuration and `calculate(observations, current_period)`).
   - Align `IndexResult`, `RouteIndex`, and `RouteAnalysis` dataclasses to match `IndexResult`, `RouteIndexResult`, `RouteContribution`, and `RouteInflationRow`.
2. `src/engine/factory.py`:
   - Replace `StubIndexEngine` and `StubRouteAnalyticsEngine` with real classes (`from index_engine import AirfarePriceIndex, AirfareAnalytics`).
3. `api/schemas.py`:
   - Update `ObservationInput` to accept the 8 required standardized fields (`observation_id`, `airline`, `origin`, `destination`, `flight_date`, `booking_date`, `total_fare`, `currency`).
   - Align `IndexCalculateResponse` and `RouteAnalysisResponse` field names (`mom_change_pct`, `yoy_change_pct`, `quality_flags`, `cleaning_report`).
4. `api/services/index_service.py` & `api/services/route_service.py`:
   - Update adapter mapping to instantiate `AirfarePriceIndex` and transform the standardized observations DataFrame.
   - Implement timeseries period iteration in `get_timeseries()`.
5. `api/routes/analytics.py`:
   - Implement the actual `/api/v1/analytics/volatility` and `/api/v1/analytics/affordability` endpoints using `AirfareAnalytics`.

### To Integrate PR #2 (`data_quality`)
1. `src/engine/protocols.py`:
   - Update `DataQualityProtocol` or define `DataQualityResult`, `SourceHealth`, and `RouteHealth` matching `src/data_quality/models.py`.
2. `src/engine/factory.py`:
   - Wrap `validate_fare_batch` in an adapter class or update `get_quality_engine()` to return a quality service wrapper.
3. `api/schemas.py`:
   - Update `QualityResponse`, `RouteHealthResponse`, and `SourceHealthResponse` to support reason codes, duplicate metrics, and 0–100 quality scoring.
4. `api/services/quality_service.py`:
   - Map between raw incoming observation batches and `validate_fare_batch()`.
5. `api/services/dashboard_service.py`:
   - Update the quality section assembly to pass `quality_result.to_dict()`.

### To Integrate PR #3 (`news_context`)
1. `src/engine/protocols.py`:
   - Update `NewsContextProtocol` to synchronous execution (or async wrapper) and adjust signature to accept route movement parameters.
2. `src/engine/factory.py`:
   - Instantiate `NewsContextService(provider=MockNewsProvider())` (or configured real provider).
3. `api/schemas.py`:
   - Update `RouteContextResponse` and `NewsEventResponse` to match `to_dashboard_dict()` (including `potential_related_factors`, `matched_signals`, `url`, `is_mock`, and `disclaimer`).
4. `api/services/news_service.py` & `api/routes/news.py`:
   - Lookup latest route inflation movement from index engine output, pass `RouteMovement` to `NewsContextService.get_context()`, and return the response.

---

## 8. Overall Readiness Assessment

| Module / PR | Readiness Status | Assessment & Rationale |
|---|---|---|
| **PR #1 (Index Engine)** | **Ready for Integration (with Service Adapter Alignment)** | The statistical engine is complete, self-contained, and thoroughly tested (88/88 passing tests) with DGCA real-world traffic data and outlier filters. Integrating it simply requires updating the thin backend adapter layer (`index_service.py` and `ObservationInput` schemas) to match the engine's real `calculate()` signature and input columns. |
| **PR #2 (Data Quality)** | **Ready for Integration (with Service Adapter Alignment)** | Clean pipeline design with 52 dedicated unit tests and an end-to-end integration test with `AirfarePriceIndex`. Sits upstream of the engine to filter raw scraped data into `valid_observations`. The backend service adapter simply needs to call `validate_fare_batch()` and map `DataQualityResult` to the quality response schema. |
| **PR #3 (News Context)** | **Ready for Integration (with Service Adapter Alignment)** | Complete multi-signal matching implementation with 28 passing unit tests and a working `MockNewsProvider`. The module is designed specifically to accept computed route movements from `index_engine` and return contextual articles with publisher URLs and legal disclaimers. Integration requires wiring `NewsContextService` to receive the route's current price change from the index engine. |
