# sih-india-airfare-price-index
Real-time Airfare Price Index for India using automated web scraping, data normalization, statistical price indexing, and CPI-aligned analysis.

## Index Engine module (`src/index_engine`)

Statistical calculation engine that turns standardized fare observations
into a national airfare price index (route indices, MoM/YoY change,
contribution analysis, quality flags). Built independently of the
scraper/database/backend/frontend so it can be integrated once those pieces
exist — see `docs/methodology.md` for the full statistical writeup.

### Setup

```bash
python -m pip install -e ".[dev,viz]"
```

### Run the tests

```bash
python -m pytest
```

### Run the end-to-end demo (synthetic data)

```bash
python examples/run_index.py       # prints the index, writes examples/last_result.json
python examples/visualize.py       # writes examples/charts.png
```

### Minimal usage

```python
from index_engine import AirfarePriceIndex

engine = AirfarePriceIndex(base_period="2026-01")  # weights default to synthetic if omitted
result = engine.calculate(observations=fares_df, current_period="2026-08")

result.national_index      # float, base_period = 100
result.mom_change_pct
result.yoy_change_pct
result.route_indices        # per-route status + index
result.to_dict()            # JSON-serializable, ready for a backend to expose
```

`fares_df` is a pandas DataFrame (or list of dicts) with columns:
`observation_id, airline, origin, destination, flight_date, booking_date,
total_fare, currency` (plus optional `fare_class`, `fare_type`, `base_fare`,
`taxes`, `fees`, `stops`, `duration`, `baggage`, `availability`, `source`,
`timestamp` — unused by the engine today but safe to pass through).
