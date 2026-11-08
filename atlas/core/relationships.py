"""Cross-metric relationship and lag exploration.

``correlation_matrix`` is the compact numeric view used by the quality screen.
``lag_analysis`` answers a harder question: does one measure move *before*
another? It tests a symmetric window of lags and reports the best absolute
correlation with a multiple-comparison caveat, because scanning many lags can
always produce a flattering number by chance.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import stats
from .semantics import pretty


def correlation_matrix(df: pd.DataFrame, columns: list[str], max_cols: int = 10) -> dict:
    names = [c for c in columns if c in df.columns][:max_cols]
    if len(names) < 2:
        raise ValueError("Choose at least two numeric columns.")
    frame = df[names].apply(pd.to_numeric, errors="coerce")
    if len(frame) > 80_000:
        frame = frame.sample(80_000, random_state=0)
    matrix: list[list[float | None]] = []
    counts: list[list[int]] = []
    for a in names:
        row: list[float | None] = []
        nrow: list[int] = []
        for b in names:
            pair = frame[[a, b]].dropna()
            if a == b:
                row.append(1.0)
                nrow.append(int(len(pair)))
                continue
            res = stats.pearson(pair[a], pair[b])
            row.append(round(float(res["r"]), 3) if res["r"] is not None else None)
            nrow.append(int(res["n"]))
        matrix.append(row)
        counts.append(nrow)
    return {
        "columns": names,
        "labels": [pretty(n) for n in names],
        "matrix": matrix,
        "counts": counts,
    }


def lag_analysis(
    df: pd.DataFrame,
    date_col: str,
    x_col: str,
    y_col: str,
    grain: str = "month",
    agg: str = "sum",
    max_lag: int = 6,
) -> dict:
    grain = grain if grain in {"day", "week", "month", "quarter"} else "month"
    agg = agg if agg in {"sum", "mean", "median"} else "sum"
    max_lag = max(1, min(int(max_lag), 24))
    frame = pd.DataFrame({
        "d": pd.to_datetime(df[date_col], errors="coerce"),
        "x": pd.to_numeric(df[x_col], errors="coerce"),
        "y": pd.to_numeric(df[y_col], errors="coerce"),
    }).dropna()
    if len(frame) < 12:
        raise ValueError("Need at least twelve dated rows to explore lags.")
    frame["p"] = _period_start(frame["d"], grain)
    grouped = frame.groupby("p")[["x", "y"]].agg(agg).sort_index()
    if len(grouped) < 8:
        raise ValueError("Need at least eight regular periods to explore lags.")
    grouped = grouped.replace([np.inf, -np.inf], np.nan).dropna()
    if len(grouped) < 8:
        raise ValueError("Not enough complete periods after cleaning.")

    x = grouped["x"].to_numpy(dtype=float)
    y = grouped["y"].to_numpy(dtype=float)
    rows = []
    for lag in range(-max_lag, max_lag + 1):
        # Positive lag: x leads y (x at t, y at t+lag).
        if lag > 0:
            pair = stats.pearson(x[:-lag], y[lag:])
            note = f"{pretty(x_col)} leads {pretty(y_col)} by {lag} {grain}{'s' if lag != 1 else ''}"
        elif lag < 0:
            pair = stats.pearson(x[-lag:], y[:lag])
            note = f"{pretty(y_col)} leads {pretty(x_col)} by {abs(lag)} {grain}{'s' if abs(lag) != 1 else ''}"
        else:
            pair = stats.pearson(x, y)
            note = "Same period"
        r = pair.get("r")
        rows.append({
            "lag": lag,
            "r": round(float(r), 3) if r is not None else None,
            "p": pair.get("p"),
            "n": pair.get("n"),
            "label": note,
        })
    valid = [row for row in rows if row["r"] is not None and row["lag"] != 0]
    best = max(valid, key=lambda row: abs(row["r"])) if valid else None
    same = next((row for row in rows if row["lag"] == 0), None)
    directional = bool(best and abs(best["r"]) > 0.3 and best["lag"] > 0)
    lead = None
    if directional:
        lead = {
            "column": x_col,
            "lag": best["lag"],
            "r": best["r"],
            "grain": grain,
            "text": f"{pretty(x_col)} tends to move {best['lag']} {grain}{'s' if best['lag'] != 1 else ''} before {pretty(y_col)}.",
        }
    narrative = (
        f"Same-period correlation between {pretty(x_col).lower()} and {pretty(y_col).lower()} is "
        f"{same['r']:.2f}." if same and same["r"] is not None else "No same-period correlation was available."
    )
    if best:
        narrative += (
            f" The strongest lag is {best['lag']:+d} {grain}{'s' if abs(best['lag']) != 1 else ''} "
            f"(r = {best['r']:.2f}). Testing {len(rows)} lags inflates the chance of a spurious "
            "peak; treat this as a hypothesis, not proof."
        )
    return {
        "date_column": date_col,
        "x_column": x_col,
        "y_column": y_col,
        "grain": grain,
        "agg": agg,
        "max_lag": max_lag,
        "rows": rows,
        "same_period_r": same["r"] if same else None,
        "best_lag": best["lag"] if best else None,
        "best_r": best["r"] if best else None,
        "lead": lead,
        "narrative": narrative,
        "series": [
            {"period": p.strftime("%Y-%m-%d"), "x": round(float(a), 2), "y": round(float(b), 2)}
            for p, a, b in zip(grouped.index, x, y)
        ],
    }


def _period_start(dates: pd.Series, grain: str) -> pd.Series:
    if grain == "day":
        return dates.dt.floor("D")
    if grain == "week":
        return dates.dt.to_period("W-MON").dt.start_time
    if grain == "quarter":
        return dates.dt.to_period("Q").dt.start_time
    return dates.dt.to_period("M").dt.start_time
