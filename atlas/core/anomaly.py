"""Anomaly detection on time series using robust, seasonally-adjusted z-scores."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .stats import robust_z
from .util import jsonable


def detect_anomalies(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    agg: str = "sum",
    threshold: float = 3.5,
    exclude_dates: list[str] | None = None,
) -> dict:
    frame = pd.DataFrame({
        "d": pd.to_datetime(df[date_col], errors="coerce"),
        "v": pd.to_numeric(df[value_col], errors="coerce"),
    }).dropna()
    excluded: list[str] = []
    if exclude_dates:
        wanted = set()
        for value in exclude_dates:
            text = str(value or "").strip()
            if not text:
                continue
            try:
                wanted.add(pd.Timestamp(text).strftime("%Y-%m-%d"))
            except (ValueError, TypeError):
                continue
        if wanted:
            excluded = sorted(wanted)
            frame = frame[~frame["d"].dt.strftime("%Y-%m-%d").isin(wanted)]
    if len(frame) < 8:
        raise ValueError("Need at least 8 observations to detect anomalies.")
    threshold = max(1.0, min(float(threshold), 8.0))
    if agg not in {"sum", "mean"}:
        agg = "sum"
    daily = frame.groupby(frame["d"].dt.floor("D"))["v"].agg(agg).sort_index()
    if len(daily) < 8:
        raise ValueError("Not enough distinct dates to detect anomalies.")
    if len(daily) > 2000:
        daily = daily.iloc[-2000:]

    # Remove a weekly pattern before scoring so Sundays are not "anomalies".
    residuals = daily.astype(float)
    if len(daily) >= 14:
        weekday_median = daily.groupby(daily.index.day_of_week).transform("median")
        if float(daily.std()) > 0 and weekday_median.notna().all():
            candidate = daily - weekday_median
            if float(candidate.std()) > float(daily.std()) * 0.15:
                residuals = candidate

    z = robust_z(residuals.to_numpy(dtype=float))
    values = daily.to_numpy(dtype=float)
    baseline = float(np.median(values))
    flagged = np.where(np.abs(z) > threshold)[0]

    series = []
    anomalies = []
    for i, (date, value) in enumerate(daily.items()):
        abs_z = float(abs(z[i])) if np.isfinite(z[i]) else 0.0
        item = {
            "date": date.strftime("%Y-%m-%d"),
            "value": round(float(value), 2),
            "z": round(abs_z, 2),
            "flag": bool(abs_z > threshold),
        }
        series.append(item)
        if abs_z > threshold:
            anomalies.append({**item, "direction": "above" if value >= baseline else "below"})

    anomalies.sort(key=lambda a: -a["z"])
    count = len(anomalies)
    return {
        "column": value_col,
        "date_column": date_col,
        "series": series[-1000:],
        "anomalies": anomalies[:40],
        "count": count,
        "baseline": round(baseline, 2),
        "threshold": threshold,
        "excluded_dates": excluded,
        "summary": _summary(anomalies, baseline),
    }


def _summary(anomalies: list[dict], baseline: float) -> str:
    if not anomalies:
        return "No statistically unusual periods detected."
    top = anomalies[0]
    multiple = top["value"] / baseline if baseline else None
    direction = "spike" if top["direction"] == "above" else "drop"
    text = f"{len(anomalies)} unusual period(s). Largest {direction}: {top['date']}"
    if multiple:
        text += f" at {multiple:.1f}× the typical level"
    text += f" (robust z = {top['z']:.1f})."
    return text
