"""
Prediction service for AI Electricity Waste Predictor.

energy_kwh in the database = kWh consumed IN THAT HOUR (hourly increment).
Daily consumption = SUM(energy_kwh) GROUP BY DATE(timestamp).

Model selection:
  >= 14 days of data  -> Linear Regression (sklearn) with chronological split
  7-13 days           -> Linear Regression but note limited data
  < 7 days            -> 7-day moving average baseline (clearly labelled)

MAE is reported only when a real test set (hold-out days) exists.
Predictions are labelled as estimates, not guaranteed accuracy.
"""
import numpy as np
from datetime import datetime, timedelta
from database.init_db import get_connection

try:
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

MIN_DAYS_FOR_ML  = 7    # minimum days before we try ML
MIN_TEST_DAYS    = 3    # minimum hold-out days to report MAE


def _fetch_daily_energy():
    """
    Return list of (date_str, daily_kwh) sorted chronologically.

    Excludes today (partial day - may have fewer readings than other days).
    Requires at least 4 readings per day to avoid noise from partial imports.
    """
    conn  = get_connection()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    rows  = conn.execute("""
        SELECT DATE(timestamp) AS day,
               SUM(energy_kwh)  AS daily_kwh,
               COUNT(*)          AS reading_count
        FROM readings
        WHERE DATE(timestamp) < ?
        GROUP BY day
        HAVING reading_count >= 4
           AND daily_kwh > 0
        ORDER BY day ASC
    """, (today,)).fetchall()
    conn.close()
    return [(r["day"], round(float(r["daily_kwh"]), 4)) for r in rows]


def _fetch_recent_hourly():
    """
    Return the last 12 hourly energy increments for next-hour prediction.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT energy_kwh FROM readings
        WHERE energy_kwh > 0
        ORDER BY timestamp DESC
        LIMIT 12
    """).fetchall()
    conn.close()
    return [float(r["energy_kwh"]) for r in reversed(rows)]


def run_prediction():
    daily  = _fetch_daily_energy()
    hourly = _fetch_recent_hourly()

    result = {
        "model_name":           "Baseline (Moving Average)",
        "trained":              False,
        "next_hour_kwh":        None,
        "next_day_kwh":         None,
        "seven_day_forecast":   [],
        "mae":                  None,
        "actual_vs_predicted":  [],
        "notes":                "",
        "data_points":          len(daily),
        "warning":              None,
    }

    # ── Next-hour prediction (simple moving average) ─────────────────────────
    if hourly:
        result["next_hour_kwh"] = round(float(np.mean(hourly[-6:])), 4)
    else:
        result["next_hour_kwh"] = 0.5

    # ── Daily prediction ─────────────────────────────────────────────────────
    if len(daily) >= MIN_DAYS_FOR_ML and SKLEARN_AVAILABLE:
        result = _run_linear_regression(result, daily)
    elif not SKLEARN_AVAILABLE:
        result["notes"]   = "scikit-learn is not installed. Using moving-average baseline."
        result["warning"] = "Install scikit-learn to enable ML predictions."
        result = _run_baseline(result, daily)
    else:
        needed = MIN_DAYS_FOR_ML - len(daily)
        result["notes"] = (
            f"Only {len(daily)} complete day(s) of data available "
            f"(need {MIN_DAYS_FOR_ML} for ML). "
            f"Add {needed} more day(s) of readings to enable Linear Regression. "
            f"Using moving-average baseline for now."
        )
        result = _run_baseline(result, daily)

    _save_prediction(result)
    return result


def _run_linear_regression(result, daily):
    dates  = [d[0] for d in daily]
    values = np.array([d[1] for d in daily], dtype=float)

    # Features: [day_index, day_of_week]
    X = np.array([
        [i, datetime.strptime(d, "%Y-%m-%d").weekday()]
        for i, d in enumerate(dates)
    ])
    y = values

    # Chronological train/test split - hold out last MIN_TEST_DAYS days
    n_test  = max(MIN_TEST_DAYS, len(y) // 5)   # ~20% test set, min MIN_TEST_DAYS
    n_test  = min(n_test, len(y) - MIN_DAYS_FOR_ML)  # must leave enough to train
    split   = len(y) - n_test

    X_train, y_train = X[:split], y[:split]
    X_test,  y_test  = X[split:], y[split:]

    model = LinearRegression()
    model.fit(X_train, y_train)

    # Evaluate on test set
    if len(X_test) >= 1:
        y_pred = model.predict(X_test)
        mae    = round(float(mean_absolute_error(y_test, y_pred)), 4)
        result["mae"] = mae
        result["actual_vs_predicted"] = [
            {
                "date":      dates[split + i],
                "actual":    round(float(y_test[i]),  4),
                "predicted": round(float(y_pred[i]),  4),
            }
            for i in range(len(y_test))
        ]

    # Forecast next 7 days
    last_idx   = len(dates)
    last_date  = datetime.strptime(dates[-1], "%Y-%m-%d")
    forecasts  = []
    for ahead in range(1, 8):
        fd    = last_date + timedelta(days=ahead)
        xf    = np.array([[last_idx + ahead - 1, fd.weekday()]])
        pred  = max(0.5, float(model.predict(xf)[0]))  # floor at 0.5 kWh/day
        forecasts.append({
            "date":          fd.strftime("%Y-%m-%d"),
            "predicted_kwh": round(pred, 4),
        })

    result["seven_day_forecast"] = forecasts
    result["next_day_kwh"]       = forecasts[0]["predicted_kwh"] if forecasts else None
    result["model_name"]         = "Linear Regression (sklearn)"
    result["trained"]            = True
    result["notes"] = (
        f"Model trained on {split} day(s). Test set: {n_test} day(s) "
        f"(chronological split - no data leakage). "
        f"Features: day index + day-of-week. "
        f"MAE = {result['mae']} kWh/day on test set."
        if result["mae"] is not None else
        f"Model trained on {split} day(s). No test-set MAE (insufficient hold-out data)."
    )
    return result


def _run_baseline(result, daily):
    """7-day moving-average baseline."""
    if len(daily) >= 1:
        window = [d[1] for d in daily[-7:]]
        avg    = round(float(np.mean(window)), 4)
    else:
        avg = 4.0  # sensible default: ~4 kWh/day for small load

    result["next_day_kwh"] = avg

    last_date = (
        datetime.strptime(daily[-1][0], "%Y-%m-%d") if daily
        else datetime.utcnow()
    )
    result["seven_day_forecast"] = [
        {
            "date":          (last_date + timedelta(days=i + 1)).strftime("%Y-%m-%d"),
            "predicted_kwh": avg,
        }
        for i in range(7)
    ]

    if len(daily) >= 3:
        result["actual_vs_predicted"] = [
            {"date": d[0], "actual": d[1], "predicted": avg}
            for d in daily[-14:]
        ]

    return result


def _save_prediction(result):
    """Persist prediction to DB."""
    conn = get_connection()
    cur  = conn.cursor()
    now  = datetime.utcnow().isoformat()
    for horizon, val in [("next_hour", result["next_hour_kwh"]),
                         ("next_day",  result["next_day_kwh"])]:
        if val is not None:
            cur.execute("""
                INSERT INTO predictions
                    (created_at, horizon, predicted_kwh, model_name, mae, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (now, horizon, val,
                  result["model_name"],
                  result.get("mae"),
                  result.get("notes", "")))
    conn.commit()
    conn.close()
