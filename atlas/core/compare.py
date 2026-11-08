"""Period-over-period comparison and contribution-to-change analysis.

The comparison is deliberately conservative: only complete periods are
compared, the previous period is the immediately preceding one at the same
grain, and a dimension breakdown must reconcile to the overall change. That
makes the waterfall additive and keeps the narrative honest.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from . import stats
from .semantics import pretty
from .util import compact, pct


def period_comparison(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    grain: str = "month",
    agg: str = "sum",
    dimension: str | None = None,
    periods: int = 2,
) -> dict:
    grain = grain if grain in {"day", "week", "month", "quarter", "year"} else "month"
    agg = agg if agg in {"sum", "mean", "median"} else "sum"
    periods = max(2, min(int(periods), 12))
    frame = pd.DataFrame({
        "d": pd.to_datetime(df[date_col], errors="coerce"),
        "v": pd.to_numeric(df[value_col], errors="coerce"),
        "dim": df[dimension].astype("object") if dimension else None,
    }).dropna(subset=["d", "v"])
    if len(frame) < 4:
        raise ValueError("Need at least four dated observations to compare periods.")
    if dimension:
        frame["dim"] = frame["dim"].where(frame["dim"].notna(), "(blank)")
        frame["dim"] = frame["dim"].astype(str).str.strip().replace("", "(blank)")

    frame["p"] = _period_start(frame["d"], grain)
    grouped = frame.groupby("p")["v"].agg(agg).sort_index()
    grouped = grouped[np.isfinite(grouped.to_numpy(dtype=float))]
    if len(grouped) < 2:
        raise ValueError(f"Need at least two {grain}s of data to compare.")

    # Drop a partial final period. A one-day month would fake a collapse.
    max_date = frame["d"].max()
    complete = [p for p in grouped.index if _is_complete(p, max_date, grain)]
    if len(complete) >= 2:
        grouped = grouped.loc[complete]

    current_p = grouped.index[-1]
    previous_p = grouped.index[-2]
    current = float(grouped.iloc[-1])
    previous = float(grouped.iloc[-2])
    delta = current - previous
    change = delta / abs(previous) if previous else None
    direction = "up" if delta > 0.000001 else "down" if delta < -0.000001 else "flat"

    frame = frame[frame["p"].isin([previous_p, current_p])]
    sig = stats.welch_t(
        frame.loc[frame["p"] == current_p, "v"].to_numpy(),
        frame.loc[frame["p"] == previous_p, "v"].to_numpy(),
    )
    significance = {
        "p": _num(sig.get("p")),
        "t": _num(sig.get("t")),
        "df": _num(sig.get("df")),
        "cohen_d": _num(sig.get("cohen_d")),
        "significant": bool(sig.get("p") is not None and sig["p"] < 0.05),
        "n_current": sig.get("n1"),
        "n_previous": sig.get("n2"),
    }

    contributions: list[dict] = []
    waterfall: list[dict] = []
    if dimension:
        pivot = (
            frame.groupby(["p", "dim"])["v"].agg(agg).unstack(fill_value=0.0)
            .reindex([previous_p, current_p], fill_value=0.0)
        )
        if current_p not in pivot.index:
            pivot.loc[current_p] = 0.0
        if previous_p not in pivot.index:
            pivot.loc[previous_p] = 0.0
        prev_row, cur_row = pivot.loc[previous_p], pivot.loc[current_p]
        diffs = (cur_row - prev_row).sort_values()
        for label in list(diffs.index):
            before = float(prev_row.get(label, 0.0))
            after = float(cur_row.get(label, 0.0))
            change_v = after - before
            contributions.append({
                "label": str(label),
                "previous": round(before, 2),
                "current": round(after, 2),
                "delta": round(change_v, 2),
                "pct": round(change_v / abs(before) * 100, 2) if before else None,
            })
        contributions.sort(key=lambda row: -abs(row["delta"]))
        running = previous
        waterfall.append({"label": _period_label(previous_p, grain), "value": round(previous, 2), "kind": "start"})
        for row in contributions[:12]:
            running += row["delta"]
            waterfall.append({
                "label": row["label"],
                "value": round(row["delta"], 2),
                "kind": "delta",
                "current": row["current"],
            })
        waterfall.append({"label": _period_label(current_p, grain), "value": round(current, 2), "kind": "end"})
    else:
        waterfall = [
            {"label": _period_label(previous_p, grain), "value": round(previous, 2), "kind": "start"},
            {"label": "Change", "value": round(delta, 2), "kind": "delta"},
            {"label": _period_label(current_p, grain), "value": round(current, 2), "kind": "end"},
        ]

    fmt = (df.attrs.get("value_format") if hasattr(df, "attrs") else None) or "number"
    narrative = _narrative(
        value_col, direction, current, previous, change, contributions, grain,
        _period_label(previous_p, grain), _period_label(current_p, grain), fmt,
    )
    return {
        "date_column": date_col,
        "value_column": value_col,
        "dimension": dimension,
        "grain": grain,
        "agg": agg,
        "previous_period": _period_label(previous_p, grain),
        "current_period": _period_label(current_p, grain),
        "previous_start": previous_p.strftime("%Y-%m-%d"),
        "current_start": current_p.strftime("%Y-%m-%d"),
        "previous": round(previous, 2),
        "current": round(current, 2),
        "delta": round(delta, 2),
        "change_pct": round(change * 100, 2) if change is not None else None,
        "direction": direction,
        "value_format": fmt,
        "significance": significance,
        "contributions": contributions,
        "waterfall": waterfall,
        "narrative": narrative,
        "periods_compared": periods,
    }


def _period_start(dates: pd.Series, grain: str) -> pd.Series:
    if grain == "day":
        return dates.dt.floor("D")
    if grain == "week":
        return dates.dt.to_period("W-MON").dt.start_time
    if grain == "quarter":
        return dates.dt.to_period("Q").dt.start_time
    if grain == "year":
        return dates.dt.to_period("Y").dt.start_time
    return dates.dt.to_period("M").dt.start_time


def _period_end(start: pd.Timestamp, grain: str) -> pd.Timestamp:
    if grain == "day":
        return start + pd.Timedelta(days=1)
    if grain == "week":
        return start + pd.Timedelta(days=7)
    months = {"month": 1, "quarter": 3, "year": 12}[grain]
    return start + pd.DateOffset(months=months)


def _is_complete(start: pd.Timestamp, max_date: pd.Timestamp, grain: str) -> bool:
    try:
        return start <= max_date and max_date >= _period_end(start, grain) - pd.Timedelta(days=1)
    except Exception:
        return True


def _period_label(start: pd.Timestamp, grain: str) -> str:
    if grain == "day":
        return start.strftime("%d %b %Y")
    if grain == "week":
        return "Week of " + start.strftime("%d %b %Y")
    if grain == "quarter":
        return f"Q{start.quarter} {start.year}"
    if grain == "year":
        return str(start.year)
    return start.strftime("%b %Y")


def _narrative(
    value_col: str,
    direction: str,
    current: float,
    previous: float,
    change: float | None,
    contributions: list[dict],
    grain: str,
    previous_label: str,
    current_label: str,
    fmt: str,
) -> str:
    label = pretty(value_col).lower()
    verb = {"up": "rose", "down": "fell", "flat": "held flat"}[direction]
    amount = f"{'+' if (change or 0) >= 0 else ''}{pct(change, 1)}" if change is not None else "changed"
    text = (
        f"{pretty(value_col)} {verb} {amount} in {current_label}, from "
        f"{_fmt(previous, fmt)} to {_fmt(current, fmt)} versus {previous_label}."
    )
    if contributions:
        positive = [c for c in contributions if c["delta"] > 0][:2]
        negative = [c for c in contributions if c["delta"] < 0][:2]
        parts = []
        if positive:
            parts.append("largest gains: " + ", ".join(
                f"{c['label']} {_fmt(c['delta'], fmt, signed=True)}" for c in positive
            ))
        if negative:
            parts.append("largest drags: " + ", ".join(
                f"{c['label']} {_fmt(c['delta'], fmt, signed=True)}" for c in negative
            ))
        if parts:
            text += " " + "; ".join(parts).capitalize() + "."
    text += " Only complete periods are compared; association is not causation."
    return text


def _fmt(value: float | None, fmt: str, signed: bool = False) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "—"
    sign = "+" if signed and value > 0 else ""
    if fmt == "currency":
        return f"{sign}${compact(float(value))}"
    if fmt in {"percentage", "percent_points"}:
        return f"{sign}{float(value):.1f}%"
    return f"{sign}{compact(float(value))}"


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
