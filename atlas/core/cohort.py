"""Cohort retention analysis.

An entity is a customer, user, account, employee — whatever the identifier
column represents. The cohort is the period of first appearance. Retention at
period *n* is the share of the cohort that appears again *n* periods later.
Revenue retention uses the same denominator but sums the value column, so a
cohort can retain more than 100% of its value through expansion.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .util import pretty


def cohort_retention(
    df: pd.DataFrame,
    entity_col: str,
    date_col: str,
    value_col: str | None = None,
    grain: str = "month",
    periods: int = 12,
) -> dict:
    grain = grain if grain in {"week", "month", "quarter", "year"} else "month"
    periods = max(2, min(int(periods), 36))
    frame = pd.DataFrame({
        "entity": df[entity_col].astype("object"),
        "d": pd.to_datetime(df[date_col], errors="coerce"),
    })
    if value_col:
        frame["value"] = pd.to_numeric(df[value_col], errors="coerce")
    frame = frame.dropna(subset=["entity", "d"])
    frame = frame[frame["entity"].astype(str).str.strip() != ""]
    if len(frame) < 8:
        raise ValueError("Need at least eight entity/date observations for cohorts.")
    if frame["entity"].nunique() < 3:
        raise ValueError("Need at least three distinct entities for cohorts.")

    frame["p"] = _period_start(frame["d"], grain)
    first = frame.groupby("entity")["p"].min().rename("cohort")
    frame = frame.join(first, on="entity")
    frame["idx"] = _period_index(frame["cohort"], frame["p"], grain)
    frame = frame[frame["idx"] >= 0]
    if frame.empty:
        raise ValueError("No usable cohort periods were found.")

    if value_col:
        cell = frame.groupby(["cohort", "idx"])["value"].sum().unstack(fill_value=0.0)
        sizes = frame.groupby("cohort")["entity"].nunique().sort_index()
        # Revenue retention is measured against the cohort's period-0 value.
        base = cell[0] if 0 in cell.columns else pd.Series(0.0, index=cell.index)
        matrix = cell.divide(base.replace(0, np.nan), axis=0) * 100
        value_label = pretty(value_col)
    else:
        cell = frame.groupby(["cohort", "idx"])["entity"].nunique().unstack(fill_value=0)
        sizes = frame.groupby("cohort")["entity"].nunique().sort_index()
        matrix = cell.divide(sizes, axis=0) * 100
        value_label = None

    cohorts = []
    for cohort in sizes.index:
        row = matrix.loc[cohort] if cohort in matrix.index else pd.Series(dtype=float)
        values = []
        for i in range(periods):
            v = row.get(i)
            values.append(None if v is None or pd.isna(v) else round(float(v), 1))
        counts = cell.loc[cohort] if cohort in cell.index else pd.Series(dtype=float)
        cohorts.append({
            "cohort": _period_label(cohort, grain),
            "cohort_start": cohort.strftime("%Y-%m-%d"),
            "size": int(sizes.loc[cohort]),
            "values": values,
            "counts": [
                None if counts.get(i) is None or pd.isna(counts.get(i))
                else int(round(float(counts.get(i))))
                for i in range(periods)
            ],
        })

    average = []
    for i in range(periods):
        column = matrix[i] if i in matrix.columns else pd.Series(dtype=float)
        column = column.dropna()
        average.append(round(float(column.mean()), 1) if len(column) else None)

    # A useful headline: period-1 retention across cohorts that have one.
    valid = [c["values"][1] for c in cohorts if len(c["values"]) > 1 and c["values"][1] is not None]
    headline = round(float(np.mean(valid)), 1) if valid else None
    latest = cohorts[-1] if cohorts else None
    narrative = (
        f"{len(cohorts)} cohorts cover {int(sizes.sum()):,} entity-period memberships. "
        f"Average period-1 retention is {headline:.1f}%."
        if headline is not None
        else f"{len(cohorts)} cohorts were identified, but not enough repeat periods to measure retention."
    )
    if latest:
        narrative += f" The newest cohort ({latest['cohort']}) starts with {latest['size']:,} entities."

    return {
        "entity_column": entity_col,
        "date_column": date_col,
        "value_column": value_col,
        "grain": grain,
        "periods": periods,
        "value_label": value_label,
        "cohorts": cohorts,
        "average": average,
        "headline_retention": headline,
        "narrative": narrative,
    }


def _period_start(dates: pd.Series, grain: str) -> pd.Series:
    if grain == "week":
        return dates.dt.to_period("W-MON").dt.start_time
    if grain == "quarter":
        return dates.dt.to_period("Q").dt.start_time
    if grain == "year":
        return dates.dt.to_period("Y").dt.start_time
    return dates.dt.to_period("M").dt.start_time


def _period_index(cohort: pd.Series, period: pd.Series, grain: str) -> pd.Series:
    if grain == "week":
        return ((period - cohort).dt.days // 7).astype("int64")
    if grain == "quarter":
        return (
            (period.dt.year - cohort.dt.year) * 4
            + (period.dt.quarter - cohort.dt.quarter)
        ).astype("int64")
    if grain == "year":
        return (period.dt.year - cohort.dt.year).astype("int64")
    return (
        (period.dt.year - cohort.dt.year) * 12
        + (period.dt.month - cohort.dt.month)
    ).astype("int64")


def _period_label(start: pd.Timestamp, grain: str) -> str:
    if grain == "week":
        return "Week of " + start.strftime("%d %b %Y")
    if grain == "quarter":
        return f"Q{start.quarter} {start.year}"
    if grain == "year":
        return str(start.year)
    return start.strftime("%b %Y")


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
