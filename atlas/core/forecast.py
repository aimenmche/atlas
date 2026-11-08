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

from .anomaly import detect_anomalies
from .util import jsonable


def forecast(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    horizon: int = 12,
    freq: str | None = None,
    agg: str = "sum",
    calendar: bool = True,
    exclude_dates: list[str] | None = None,
    include_anomalies: bool = True,
) -> dict:
    horizon = max(1, min(int(horizon), 60))
    if agg not in {"sum", "mean"}:
        agg = "sum"
    frame = pd.DataFrame({
        "d": pd.to_datetime(df[date_col], errors="coerce"),
        "v": pd.to_numeric(df[value_col], errors="coerce"),
    }).dropna()
    excluded: list[str] = []
    if exclude_dates:
        wanted = {_date_key(value) for value in exclude_dates if _date_key(value)}
        if wanted:
            mask = ~frame["d"].dt.strftime("%Y-%m-%d").isin(wanted)
            excluded = sorted(wanted)
            frame = frame[mask]
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
    calendar_effects = _calendar_effects(series) if calendar else {}
    if len(series) > 1200:
        series = series.iloc[-1200:]

    y = series.to_numpy(dtype=float)
    n = len(y)
    period = _seasonal_period(label, n)
    split = max(5, int(n * 0.8))
    train, test = y[:split], y[split:]

    candidates: list[dict] = []
    if period > 1 and len(train) >= period + 3:
        hw = {"mae": float("inf"), "params": None, "model": None, "sigma": None}
        for alpha in (0.1, 0.3, 0.5, 0.7, 0.9):
            for beta in (0.05, 0.2, 0.5, 0.8):
                for gamma in (0.1, 0.4, 0.8):
                    fitted, sigma = _holt_winters(train, period, alpha, beta, gamma)
                    if not fitted:
                        continue
                    pred = _hw_forecast(fitted, period, len(test))
                    mae = float(np.mean(np.abs(pred - test)))
                    if mae < hw["mae"]:
                        hw = {
                            "mae": mae,
                            "params": (alpha, beta, gamma),
                            "model": f"Holt-Winters additive (season {period})",
                            "sigma": sigma,
                        }
        if hw["model"]:
            candidates.append({
                **hw,
                "key": "holt-winters",
                "mape": _mape(test, _predict_test(train, hw["model"], period, hw, len(test))),
            })

    # Seasonal-naive baseline
    if period > 1 and len(train) > period:
        naive = np.array([train[len(train) - period + (h % period)] for h in range(len(test))])
        candidates.append({
            "model": "Seasonal naive",
            "key": "seasonal-naive",
            "mae": float(np.mean(np.abs(naive - test))),
            "mape": _mape(test, naive),
            "params": None,
            "sigma": float(np.std(np.diff(train))) or None,
        })

    # Linear trend is always a candidate, not merely a fallback.
    x_train = np.arange(len(train), dtype=float)
    slope, intercept = np.polyfit(x_train, train, 1)
    linear_pred = slope * np.arange(len(train), len(train) + len(test)) + intercept
    candidates.append({
        "model": "Linear trend",
        "key": "linear",
        "mae": float(np.mean(np.abs(linear_pred - test))),
        "mape": _mape(test, linear_pred),
        "params": None,
        "sigma": float(np.std(train - (slope * x_train + intercept))) or None,
    })

    if not candidates:
        raise ValueError("Not enough regular periods to select a model.")
    selected = min(candidates, key=lambda item: item["mae"])
    best = selected
    model = best["model"]
    sigma = best["sigma"] or float(np.std(train)) or 1.0
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

    backtest, interval = _backtest(y, split, period, model, best, float(sigma))
    interval_scale = interval["scale"] if interval else 1.0

    non_negative = bool(np.all(y >= 0))
    forecast_rows = []
    for h, (date, value) in enumerate(zip(future_dates, preds), start=1):
        half = 1.96 * float(sigma) * math.sqrt(h) * interval_scale
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

    comparison = []
    for candidate in sorted(candidates, key=lambda item: item["mae"]):
        comparison.append({
            "model": candidate["model"],
            "key": candidate["key"],
            "mae": round(float(candidate["mae"]), 2),
            "mape": round(float(candidate["mape"]), 2) if candidate.get("mape") is not None else None,
            "selected": candidate is selected,
            "rationale": (
                "Lowest holdout MAE"
                if candidate is selected
                else "Higher holdout error than the selected model"
            ),
        })

    last = float(y[-1])
    next_value = float(preds[0]) if len(preds) else last
    change = (next_value - last) / abs(last) if last else None
    history = [
        {"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 2)}
        for d, v in series.items()
    ]

    detected: list[dict] = []
    if include_anomalies:
        try:
            scan = detect_anomalies(frame, date_col, value_col, agg=agg, threshold=3.0)
            detected = scan.get("anomalies") or []
        except (ValueError, KeyError):
            detected = []

    warnings = []
    if n < 24:
        warnings.append("Short series: intervals are wide and seasonality may be unreliable.")
    if interval and interval_scale > 1.25:
        warnings.append(
            "Backtest intervals were narrower than reality; prediction intervals were widened "
            f"by {interval_scale:.2f}×."
        )
    if excluded:
        warnings.append(f"Excluded {len(excluded)} requested date(s) from the model fit.")

    return {
        "column": value_col,
        "date_column": date_col,
        "frequency": label,
        "model": model,
        "horizon": horizon,
        "seasonality": period,
        "history": history[-400:],
        "forecast": forecast_rows,
        "candidates": comparison,
        "backtest": backtest,
        "interval": interval,
        "calendar": calendar_effects,
        "excluded_dates": excluded,
        "anomalies": detected,
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
        "warnings": warnings,
    }


def _backtest(
    y: np.ndarray,
    split: int,
    period: int,
    model: str,
    best: dict,
    sigma: float,
) -> tuple[list[dict], dict | None]:
    """Rolling-origin backtest used to calibrate the prediction intervals."""
    n = len(y)
    test_len = n - split
    if test_len < 2 or sigma <= 0:
        return [], None
    step = max(1, test_len // 3)
    folds: list[dict] = []
    normalised: list[float] = []
    for fold in range(3):
        end = split + fold * step
        if end >= n:
            break
        actual = y[end:min(n, end + step)]
        if len(actual) < 1:
            continue
        predicted = _predict_test(y[:end], model, period, best, len(actual))
        if len(predicted) != len(actual):
            continue
        errors = actual - predicted
        steps = np.arange(1, len(actual) + 1, dtype=float)
        norm = np.abs(errors) / (sigma * np.sqrt(steps))
        if not np.all(np.isfinite(norm)):
            continue
        normalised.extend(float(value) for value in norm)
        folds.append({
            "fold": fold + 1,
            "train_points": int(end),
            "test_points": int(len(actual)),
            "mae": round(float(np.mean(np.abs(errors))), 2),
            "mape": round(float(_mape(actual, predicted) or 0.0), 2),
            "coverage": round(float(np.mean(norm <= 1.96)), 3),
        })
    if not normalised:
        return folds, None
    coverage = float(np.mean(np.asarray(normalised) <= 1.96))
    quantile = float(np.quantile(normalised, 0.95))
    scale = float(np.clip(quantile / 1.96, 0.75, 2.5))
    return folds, {
        "nominal": 95,
        "empirical_coverage": round(coverage, 3),
        "scale": round(scale, 2),
        "points": len(normalised),
        "method": "rolling-origin backtest",
    }


def _calendar_effects(series: pd.Series) -> dict:
    """Describe weekday, month and fixed-holiday effects in the history."""
    if len(series) < 14:
        return {"note": "Not enough history to estimate calendar effects."}
    overall = float(series.mean())
    median = float(series.median())
    if overall == 0:
        return {"note": "The series averages zero; calendar effects are undefined."}
    by_weekday = series.groupby(series.index.day_name()).mean()
    by_month = series.groupby(series.index.month).mean()
    weekday = {
        str(name): round(float(value / overall - 1.0) * 100, 1)
        for name, value in by_weekday.items()
    }
    month = {
        str(int(name)): round(float(value / overall - 1.0) * 100, 1)
        for name, value in by_month.items()
    }
    fixed = {
        "01-01": "New Year's Day",
        "07-04": "Independence Day",
        "12-24": "Christmas Eve",
        "12-25": "Christmas Day",
        "12-31": "New Year's Eve",
    }
    holidays = []
    for date, value in series.items():
        key = date.strftime("%m-%d")
        if key not in fixed or median == 0:
            continue
        holidays.append({
            "date": date.strftime("%Y-%m-%d"),
            "name": fixed[key],
            "value": round(float(value), 2),
            "lift": round(float(value / median - 1.0) * 100, 1),
        })
    holidays.sort(key=lambda item: abs(item["lift"]), reverse=True)
    return {
        "weekday_effect_pct": weekday,
        "month_effect_pct": month,
        "holidays": holidays[:8],
        "note": "Descriptive effects versus the series mean; the model does not add holiday regressors.",
    }


def _date_key(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return pd.Timestamp(text).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return ""


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
