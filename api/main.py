"""FastAPI wrapper around index_engine.

This is a thin integration layer, not part of the statistical engine
itself: it only translates HTTP JSON <-> the engine's plain Python/pandas
interface, so the backend teammate has a stable HTTP contract to build the
dashboard against without needing to import Python directly.

Run locally:

    uvicorn api.main:app --reload --port 8000

Then open http://127.0.0.1:8000/docs for interactive Swagger docs.
"""

from __future__ import annotations

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from index_engine import AirfarePriceIndex, IndexConfig, InsufficientDataError, __version__

from .schemas import (
    CalculateRequest,
    IndexResultOut,
    TimeseriesRequest,
)

app = FastAPI(
    title="Airfare Price Index API",
    description=(
        "HTTP wrapper around the SIH Airfare Price Index statistical engine. "
        "Prototype only — see /docs and the repo's docs/methodology.md."
    ),
    version=__version__,
)

# Prototype-only: wide open CORS so the dashboard teammate can hit this from
# any local dev origin without configuration. Tighten before any real deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_config(base_period: str, config_in) -> IndexConfig:
    if config_in is None:
        return IndexConfig(base_period=base_period)
    return IndexConfig(base_period=base_period, **config_in.model_dump())


def _build_weights(weights_in):
    if not weights_in:
        return None
    return pd.DataFrame([w.model_dump() for w in weights_in])


def _build_observations(observations_in) -> pd.DataFrame:
    return pd.DataFrame([obs.model_dump() for obs in observations_in])


@app.get("/health")
def health():
    return {"status": "ok", "index_engine_version": __version__}


@app.post("/index/calculate", response_model=IndexResultOut)
def calculate_index(request: CalculateRequest):
    """Calculate the airfare index for a single current_period vs. base_period."""
    config = _build_config(request.base_period, request.config)
    weights = _build_weights(request.weights)
    observations = _build_observations(request.observations)

    engine = AirfarePriceIndex(base_period=request.base_period, weights=weights, config=config)
    try:
        result = engine.calculate(observations=observations, current_period=request.current_period)
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result.to_dict()


@app.post("/index/timeseries", response_model=list[IndexResultOut])
def calculate_timeseries(request: TimeseriesRequest):
    """Calculate the index for a list of periods in one call, e.g. for a
    dashboard's "index over time" chart — avoids re-uploading observations
    per period."""
    config = _build_config(request.base_period, request.config)
    weights = _build_weights(request.weights)
    observations = _build_observations(request.observations)

    engine = AirfarePriceIndex(base_period=request.base_period, weights=weights, config=config)
    results = []
    for period in request.periods:
        try:
            result = engine.calculate(observations=observations, current_period=period)
        except InsufficientDataError as exc:
            raise HTTPException(status_code=422, detail=f"Period {period}: {exc}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Period {period}: {exc}") from exc
        results.append(result.to_dict())
    return results
