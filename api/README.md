# sih-backend — India Airfare Price Index API

FastAPI backend for the India Airfare Price Index (SIH) project. This is a **thin integration layer** that exposes the Index Engine and related modules to a frontend dashboard.

## Quick Start

```bash
# 1. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env
# Edit .env and set API_KEY to a secret value

# 4. Run the dev server
uvicorn api.main:app --reload

# 5. Open Swagger UI
# http://localhost:8000/docs
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/index/calculate` | Calculate the airfare price index |
| `GET`  | `/api/v1/index/timeseries` | Retrieve index time series |
| `GET`  | `/api/v1/routes` | Route-level analysis |
| `GET`  | `/api/v1/quality` | Data quality report |
| `GET`  | `/api/v1/routes/{route}/context` | News/event context for a route |
| `GET`  | `/api/v1/dashboard/summary` | Aggregated dashboard summary |
| `GET`  | `/health` | Health check (no auth required) |

## Authentication

All `/api/v1/*` endpoints require an `X-API-Key` header matching the `API_KEY` environment variable.

```bash
curl -H "X-API-Key: your-key" http://localhost:8000/api/v1/routes
```

## Swapping Stubs for Real Engines

The backend ships with **stub implementations** that return synthetic data (clearly labeled `data_source: "synthetic"` in every response). When the real Index Engine and sibling modules are ready:

1. Open [`src/engine/factory.py`](../src/engine/factory.py)
2. Import your real implementation classes
3. Update the `get_*()` factory functions to return the real instances
4. No changes needed in routes, services, or schemas

The engine interfaces are defined as `typing.Protocol` classes in [`src/engine/protocols.py`](../src/engine/protocols.py). Your real implementations just need to match the method signatures — no inheritance required.

## Testing

```bash
pytest tests/ -v
```

## Project Structure

```
api/
├── main.py              # FastAPI app, CORS, router mounts
├── schemas.py            # Pydantic request/response models
├── dependencies.py       # API key auth
├── routes/
│   ├── index.py          # /index/calculate, /index/timeseries
│   ├── routes.py         # /routes
│   ├── quality.py        # /quality
│   ├── news.py           # /routes/{route}/context
│   ├── analytics.py      # Placeholder for future analytics
│   └── dashboard.py      # /dashboard/summary
└── services/
    ├── index_service.py
    ├── quality_service.py
    ├── route_service.py
    ├── news_service.py
    └── dashboard_service.py

src/
└── engine/
    ├── protocols.py      # Protocol interfaces
    ├── stubs.py          # Stub implementations (synthetic)
    └── factory.py        # Swap stubs ↔ real engines here

tests/
requirements.txt
.env.example
```
