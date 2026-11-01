"""Time-series forecasting with backtested model selection.

Implements Holt-Winters (additive) and a seasonal-naive baseline in NumPy,
selects between them on a holdout window, and returns prediction intervals.
No SciPy or statsmodels required.
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd

from .util import jsonable


def forecast(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    horizon: int = 12,
    freq: str | None = None,
    agg: str = "sum",
) -> dict:
    horizon = max(1, min(int(horizon), 60))
    if agg not in {"sum", "mean"}:
        agg = "sum"
    frame = pd.DataFrame({
        "d": pd.to_datetime(df[date_col], errors="coerce"),
        "v": pd.to_numeric(df[value_col], errors="coerce"),
    }).dropna()
    if len(frame) < 8:
        raise ValueError("Need at least 8 observations to forecast.")

    rule, label = _frequency(frame["d"], freq)
    grouped = frame.set_index("d").resample(rule)
    series = grouped["v"].agg(agg)
    counts = grouped.size()
    if len(series) >= 6:
        median_count = float(counts.median())
        keep = counts[counts >= max(1.0, median_count * 0.5)].index
        series = series.loc[keep]
    if agg == "sum":
        series = series.fillna(0.0)
    else:
        series = series.dropna()
    series = series[series.index.notna()]
    if len(series) < 8:
        raise ValueError("Not enough regular periods to forecast.")
    if len(series) > 1200:
        series = series.iloc[-1200:]

    y = series.to_numpy(dtype=float)
    n = len(y)
    period = _seasonal_period(label, n)
    split = max(5, int(n * 0.8))
    train, test = y[:split], y[split:]

    best = {"mae": float("inf"), "params": None, "model": None, "sigma": None}
    if period > 1 and len(train) >= period + 3:
        for alpha in (0.1, 0.3, 0.5, 0.7, 0.9):
            for beta in (0.05, 0.2, 0.5, 0.8):
                for gamma in (0.1, 0.4, 0.8):
                    fitted, sigma = _holt_winters(train, period, alpha, beta, gamma)
                    if not fitted:
                        continue
                    pred = _hw_forecast(fitted, period, len(test))
                    mae = float(np.mean(np.abs(pred - test)))
                    if mae < best["mae"]:
                        best = {
                            "mae": mae,
                            "params": (alpha, beta, gamma),
                            "model": f"Holt-Winters additive (season {period})",
                            "sigma": sigma,
                        }
    # Seasonal-naive baseline
    if period > 1 and len(train) > period:
        naive = []
        for h in range(len(test)):
            naive.append(train[len(train) - period + (h % period)])
        mae = float(np.mean(np.abs(np.array(naive) - test)))
        if mae < best["mae"]:
            best = {"mae": mae, "params": None, "model": "Seasonal naive", "sigma": None}
    # Linear fallback
    if best["params"] is None and best["model"] is None:
        x = np.arange(len(train), dtype=float)
        slope, intercept = np.polyfit(x, train, 1)
        pred = slope * np.arange(len(train), len(train) + len(test)) + intercept
        mae = float(np.mean(np.abs(pred - test)))
        best = {"mae": mae, "params": None, "model": "Linear trend", "sigma": float(np.std(train - (slope * x + intercept)))}

    model = best["model"] or "Linear trend"
    sigma = best["sigma"]
    future_dates = _future_index(series.index[-1], rule, horizon)

    if model.startswith("Holt-Winters"):
        alpha, beta, gamma = best["params"]
        fitted, sigma = _holt_winters(y, period, alpha, beta, gamma)
        if sigma is None:
            sigma = float(np.std(y - np.mean(y))) or 1.0
        preds = _hw_forecast(fitted, period, horizon)
    elif model == "Seasonal naive":
        fitted = None
        sigma = float(np.std(np.diff(y))) or 1.0
        preds = [y[n - period + (h % period)] for h in range(horizon)]
    else:
        x = np.arange(n, dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        preds = list(slope * np.arange(n, n + horizon) + intercept)
        sigma = sigma or float(np.std(y - (slope * x + intercept))) or 1.0

    non_negative = bool(np.all(y >= 0))
    forecast_rows = []
    for h, (date, value) in enumerate(zip(future_dates, preds), start=1):
        half = 1.96 * float(sigma) * math.sqrt(h)
        lo, hi = value - half, value + half
        if non_negative:
            lo = max(0.0, lo)
        forecast_rows.append({
            "date": date.strftime("%Y-%m-%d"),
            "value": round(float(value), 2),
            "lower": round(float(lo), 2),
            "upper": round(float(hi), 2),
        })

    y_hat = _in_sample(y, model, period, best, sigma)
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    mape = _mape(test, _predict_test(train, model, period, best, len(test)))

    last = float(y[-1])
    next_value = float(preds[0]) if len(preds) else last
    change = (next_value - last) / abs(last) if last else None
    history = [
        {"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 2)}
        for d, v in series.items()
    ]
    return {
        "column": value_col,
        "date_column": date_col,
        "frequency": label,
        "model": model,
        "horizon": horizon,
        "seasonality": period,
        "history": history[-400:],
        "forecast": forecast_rows,
        "metrics": {
            "mae": round(float(best["mae"]), 2),
            "mape": round(mape, 2) if mape is not None else None,
            "r2": round(max(0.0, min(1.0, r2)), 3),
            "holdout_points": len(test),
        },
        "summary": {
            "last": round(last, 2),
            "next": round(next_value, 2),
            "change_pct": round(change * 100, 2) if change is not None else None,
            "direction": "up" if change and change > 0.01 else "down" if change and change < -0.01 else "flat",
            "average_forecast": round(float(np.mean(preds)), 2),
        },
        "warnings": (
            ["Short series: intervals are wide and seasonality may be unreliable."]
            if n < 24 else []
        ),
    }


def _frequency(dates: pd.Series, freq: str | None) -> tuple[str, str]:
    if freq in {"D", "W", "M", "Q"}:
        return {"D": ("D", "daily"), "W": ("W-MON", "weekly"), "M": ("MS", "monthly"), "Q": ("QS", "quarterly")}[freq]
    unique = dates.dropna().drop_duplicates().sort_values()
    gaps = unique.diff().dt.total_seconds().div(86400).dropna()
    median = float(gaps.median()) if len(gaps) else 1.0
    if median <= 1.5:
        return "D", "daily"
    if median <= 8:
        return "W-MON", "weekly"
    if median <= 32:
        return "MS", "monthly"
    return "QS", "quarterly"


def _seasonal_period(label: str, n: int) -> int:
    if label == "daily" and n >= 14:
        return 7
    if label == "weekly":
        if n >= 110:
            return 52
        if n >= 30:
            return 13
    if label == "monthly" and n >= 18:
        return 12
    if label == "quarterly" and n >= 10:
        return 4
    return 1


def _future_index(last, rule: str, horizon: int) -> list[pd.Timestamp]:
    freq = {"D": "D", "W-MON": "W-MON", "MS": "MS", "QS": "QS"}[rule]
    return list(pd.date_range(last, periods=horizon + 1, freq=freq)[1:])


def _holt_winters(y: np.ndarray, m: int, alpha: float, beta: float, gamma: float):
    n = len(y)
    if n < m + 3:
        return None, None
    season_means = [float(np.mean(y[:m]))]
    if n >= 2 * m:
        season_means.append(float(np.mean(y[m:2 * m])))
        trend = (season_means[1] - season_means[0]) / m
    else:
        trend = (float(y[-1]) - float(y[0])) / max(1, n - 1)
    level = season_means[0]
    seasonal = list(y[:m] - level)
    errors = []
    fitted_values = []
    for i in range(n):
        s = seasonal[i % m]
        pred = level + trend + s
        fitted_values.append(pred)
        if i >= m:
            errors.append(y[i] - pred)
        new_level = alpha * (y[i] - s) + (1 - alpha) * (level + trend)
        new_trend = beta * (new_level - level) + (1 - beta) * trend
        seasonal[i % m] = gamma * (y[i] - new_level) + (1 - gamma) * s
        level, trend = new_level, new_trend
    sigma = float(np.std(errors)) if errors else float(np.std(y)) or 1.0
    return {"level": level, "trend": trend, "seasonal": seasonal, "fitted": fitted_values}, sigma


def _hw_forecast(model: dict, m: int, horizon: int) -> list[float]:
    level, trend, seasonal = model["level"], model["trend"], model["seasonal"]
    n = len(seasonal)
    return [level + h * trend + seasonal[(n + h - 1) % m] for h in range(1, horizon + 1)]


def _predict_test(train, model_name, period, best, steps):
    if model_name.startswith("Holt-Winters"):
        fitted, _ = _holt_winters(train, period, *best["params"])
        return np.array(_hw_forecast(fitted, period, steps)) if fitted else np.array([])
    if model_name == "Seasonal naive" and len(train) > period:
        return np.array([train[len(train) - period + (h % period)] for h in range(steps)])
    x = np.arange(len(train), dtype=float)
    slope, intercept = np.polyfit(x, train, 1)
    return slope * np.arange(len(train), len(train) + steps) + intercept


def _in_sample(y, model_name, period, best, sigma):
    if model_name.startswith("Holt-Winters") and best["params"]:
        fitted, _ = _holt_winters(y, period, *best["params"])
        if fitted:
            return np.asarray(fitted["fitted"], dtype=float)
    if model_name == "Seasonal naive" and period > 1 and len(y) > period:
        return np.asarray([y[i - period] if i >= period else np.mean(y[:period]) for i in range(len(y))], dtype=float)
    if model_name == "Linear trend":
        x = np.arange(len(y), dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        return slope * x + intercept
    return np.full(len(y), float(np.mean(y)))


def _mape(actual: Iterable[float], predicted: Iterable[float]) -> float | None:
    a, p = np.asarray(list(actual), dtype=float), np.asarray(list(predicted), dtype=float)
    if len(a) == 0 or len(a) != len(p):
        return None
    mask = np.abs(a) > 1e-9
    if not mask.any():
        return None
    return float(np.mean(np.abs((a[mask] - p[mask]) / a[mask])) * 100)
