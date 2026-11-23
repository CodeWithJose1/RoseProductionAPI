"""Moving-average production forecasting (FR-07).

Method (documented in TC-07 of the project report):

    estimate = (q1 + q2 + ... + qN) / N

where q1..qN are the quantities of the N most recent harvest records of the
same crop whose harvest_date is strictly earlier than the forecast date
(N = 3 by default). Ties on the same date are ordered by harvest_id.

Assumptions and limits:
* Only real Harvest rows are used; nothing is interpolated or invented.
* If fewer than N earlier harvests exist the forecast is refused (400)
  instead of being computed from a shorter history.
* The method does not model trend or seasonality; it is a baseline.
* The result is rounded to 2 decimals (Forecast.estimated_quantity is
  DECIMAL(12,2)).

Verified against the data: this procedure reproduces exactly the seven
forecasts already stored in RoseProductionDB with the method
"Moving Average (3 records)" (see tests/test_api_forecasting.py).
"""

from decimal import ROUND_HALF_UP, Decimal

from errors import ApiError
from models import Harvest

DEFAULT_WINDOW = 3
MIN_WINDOW = 1
MAX_WINDOW = 12


def method_label(window):
    # Same label as the forecasts already stored in RoseProductionDB.
    return f"Moving Average ({window} records)"


def moving_average(crop_id, forecast_date, window=DEFAULT_WINDOW):
    history = (
        Harvest.query
        .filter(Harvest.crop_id == crop_id,
                Harvest.harvest_date < forecast_date)
        .order_by(Harvest.harvest_date.desc(), Harvest.harvest_id.desc())
        .limit(window)
        .all()
    )

    if len(history) < window:
        raise ApiError(
            400,
            f"Not enough history: the moving average needs {window} "
            f"harvest record(s) of this crop before "
            f"{forecast_date.isoformat()}, but only {len(history)} "
            f"exist.",
            details={"forecast_date": "insufficient earlier harvests",
                     "available_harvests": len(history),
                     "required_harvests": window},
            code="INSUFFICIENT_HISTORY",
        )

    total = sum(h.quantity for h in history)
    estimate = (Decimal(total) / Decimal(window)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return {
        "estimated_quantity": float(estimate),
        "window": window,
        "method": method_label(window),
        "formula": f"({' + '.join(str(h.quantity) for h in history)})"
                   f" / {window} = {estimate}",
        "history": [
            {
                "harvest_id": h.harvest_id,
                "harvest_date": h.harvest_date.isoformat(),
                "quantity": h.quantity,
                "season": h.season.name,
            }
            for h in history
        ],
    }, estimate
