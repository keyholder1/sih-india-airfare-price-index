"""Result dataclasses for the baseline forecasting stage.

Mirrors index_engine.models' conventions on purpose: plain dataclasses,
``.to_dict()`` for JSON-serializable output, ``Optional`` for anything not
legitimately computable, explicit ``status`` fields, and nothing
fabricated. Kept in their own module (not mixed into model or backtesting
logic) the same way index_engine separates models.py from the modules
that populate it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional

STATUS_OK = "OK"
STATUS_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
STATUS_MODEL_NOT_APPLICABLE = "MODEL_NOT_APPLICABLE"
#: A specific, distinct reason a backtest fold was skipped: the target
#: period itself has no trustworthy value to score against (missing or
#: filtered out by a quality threshold) — different from
#: STATUS_MODEL_NOT_APPLICABLE, where the target is fine but the model
#: couldn't produce a forecast from the training window.
STATUS_TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"


@dataclass
class ForecastResult:
    """A single forecast produced by a baseline model.

    Every forecast produced by this stage is against the current 8-month
    SYNTHETIC sample dataset — ``is_synthetic_data`` exists specifically
    so no downstream consumer (dashboard, report, teammate) forgets that
    and presents it as a real prediction.

    ``lower_bound``/``upper_bound`` are ``None`` unless a genuine,
    backtest-derived interval could be computed — never a fabricated
    formula-based interval with no empirical support.
    """

    forecast_period: str
    forecast_value: Optional[float]
    model_used: str
    horizon: int
    training_period: List[str]
    data_points_used: int
    lower_bound: Optional[float]
    upper_bound: Optional[float]
    status: str
    is_synthetic_data: bool
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ModelEvaluationResult:
    """Rolling-origin backtest summary for one baseline model.

    ``mase``/``mase_status`` are always both present: if MASE cannot be
    legitimately computed on the available history, ``mase`` is ``None``
    and ``mase_status`` explains exactly why, rather than the field simply
    being absent.
    """

    model: str
    number_of_forecasts: int
    mae: Optional[float]
    rmse: Optional[float]
    mase: Optional[float]
    mase_status: str
    status: str
    notes: Optional[str] = None
    forecasts: List[ForecastResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
