"""Dataset profiling: schema, distributions, missingness, correlations, quality."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import stats
from .quality import build_quality
from .semantics import detect, is_measure
from .util import jsonable, pretty


def build_profile(df: pd.DataFrame, dataset_id: str, name: str) -> dict:
    columns = [_profile_column(df, col) for col in df.columns]
    quality = build_quality(df, columns)
    time_info = _time_info(df, columns)
    correlations = _correlation_block(df, columns)
    rows, cols = len(df), len(df.columns)
    dup_rows = int(df.duplicated().sum())

    semantic_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    for col in columns:
        semantic_counts[col["semantic"]] = semantic_counts.get(col["semantic"], 0) + 1
        role_counts[col["role"]] = role_counts.get(col["role"], 0) + 1

    return {
        "id": dataset_id,
        "name": name,
        "rows": rows,
        "cols": cols,
        "memory_bytes": int(df.memory_usage(deep=True).sum()),
        "duplicate_rows": dup_rows,
        "duplicate_pct": round(dup_rows / rows * 100, 2) if rows else 0.0,
        "columns": columns,
        "time": time_info,
        "correlations": correlations,
        "missingness": sorted(
            [{"column": c["name"], "missing_pct": c["null_pct"], "missing": c["null_count"]} for c in columns],
            key=lambda x: -x["missing_pct"],
        ),
        "quality": quality,
        "semantic_counts": semantic_counts,
        "role_counts": role_counts,
        "measures": [c["name"] for c in columns if is_measure(c)],
        "dimensions": [c["name"] for c in columns if c["role"] == "dimension"],
        "time_columns": [c["name"] for c in columns if c["role"] == "time"],
    }


def _profile_column(df: pd.DataFrame, name: str) -> dict:
    s = df[name]
    sem = detect(name, s, s.dtype)
    non_null = s.dropna()
    n = int(non_null.size)
    rows = max(1, len(s))
    distinct = int(non_null.nunique()) if n else 0
    null_count = int(len(s) - n)

    col = {
        "name": name,
        "label": pretty(name),
        "dtype": _friendly_dtype(sem, s),
        "semantic": sem["semantic"],
        "role": sem["role"],
        "confidence": round(float(sem.get("confidence", 0.5)), 2),
        "pii": bool(sem.get("pii", False)),
        "null_count": null_count,
        "null_pct": round(null_count / rows * 100, 2),
        "distinct": distinct,
        "distinct_pct": round(distinct / n * 100, 1) if n else 0.0,
        "examples": [_sample(v) for v in non_null.head(3).tolist()],
        "flags": [],
    }
    if distinct <= 1:
        col["flags"].append("constant")
    if n and distinct / n > 0.95 and sem["role"] == "text":
        col["flags"].append("high_cardinality")

    if sem["role"] == "time" or pd.api.types.is_datetime64_any_dtype(s):
        _add_date_stats(col, s)
    elif sem["semantic"] == "boolean" or pd.api.types.is_bool_dtype(s):
        true_count = int((non_null.astype(str).str.lower().isin(["true", "yes", "y", "1", "t"])).sum()) if n else 0
        col["boolean"] = {
            "true": true_count,
            "false": int(n - true_count),
            "true_pct": round(true_count / n * 100, 1) if n else 0.0,
        }
        col["top_values"] = _top_values(non_null)
    elif pd.api.types.is_numeric_dtype(s) and sem["role"] != "identifier":
        _add_numeric_stats(col, pd.to_numeric(s, errors="coerce"))
    else:
        col["top_values"] = _top_values(non_null)
        if n:
            lengths = non_null.astype(str).str.len()
            col["text"] = {
                "avg_length": round(float(lengths.mean()), 1),
                "max_length": int(lengths.max()),
            }
    return col


def _add_numeric_stats(col: dict, s: pd.Series) -> None:
    values = pd.to_numeric(s, errors="coerce").dropna()
    desc = stats.describe(values)
    col["stats"] = {k: _round(v) for k, v in desc.items()}
    sample = values.sample(min(len(values), 50_000), random_state=0) if len(values) > 50_000 else values
    col["histogram"] = stats.histogram(sample)
    col["outliers"] = stats.outlier_count(sample)
    col["outlier_pct"] = round(col["outliers"] / max(1, len(sample)) * 100, 2)
    col["zeros"] = int((sample == 0).sum())
    col["negatives"] = int((sample < 0).sum())
    col["top_values"] = _top_values(values, limit=5) if values.nunique() <= 12 else []


def _add_date_stats(col: dict, s: pd.Series) -> None:
    values = pd.to_datetime(s, errors="coerce").dropna()
    if values.empty:
        col["date"] = {}
        return
    diffs = values.sort_values().diff().dropna().dt.total_seconds() / 86400
    median_step = float(diffs.median()) if len(diffs) else 1.0
    granularity = (
        "day" if median_step <= 1.5 else
        "week" if median_step <= 8 else
        "month" if median_step <= 32 else
        "quarter" if median_step <= 100 else "year"
    )
    col["date"] = {
        "min": jsonable(values.min()),
        "max": jsonable(values.max()),
        "span_days": int((values.max() - values.min()).days),
        "granularity": granularity,
        "periods": int(values.nunique()),
    }
    col["top_values"] = _top_values(values)


def _time_info(df: pd.DataFrame, columns: list[dict]) -> dict | None:
    candidates = [c for c in columns if c["role"] == "time" and c.get("date")]
    if not candidates:
        return None
    candidates.sort(key=lambda c: c["date"].get("periods", 0), reverse=True)
    best = candidates[0]
    d = best["date"]
    return {
        "column": best["name"],
        "min": d["min"],
        "max": d["max"],
        "span_days": d["span_days"],
        "granularity": d["granularity"],
        "periods": d["periods"],
    }


def _correlation_block(df: pd.DataFrame, columns: list[dict], max_cols: int = 18) -> dict:
    numeric = [c for c in columns if is_measure(c)]
    numeric.sort(key=lambda c: ({"currency": 0, "count": 1, "percentage": 2}.get(c["semantic"], 3)))
    selected = numeric[:max_cols]
    if len(selected) < 2:
        return {"columns": [], "matrix": [], "labels": []}
    names = [c["name"] for c in selected]
    frame = df[names].apply(pd.to_numeric, errors="coerce")
    if len(frame) > 60_000:
        frame = frame.sample(60_000, random_state=0)
    corr = frame.corr(min_periods=10)
    matrix: list[list[float | None]] = []
    for i in range(len(names)):
        row = []
        for j in range(len(names)):
            v = corr.iloc[i, j]
            row.append(None if pd.isna(v) else round(float(v), 3))
        matrix.append(row)
    return {"columns": names, "labels": [pretty(n) for n in names], "matrix": matrix}


def _top_values(s: pd.Series, limit: int = 12) -> list[dict]:
    if s.empty:
        return []
    counts = s.value_counts(dropna=True).head(limit)
    total = int(s.notna().sum()) or 1
    return [
        {"value": _sample(idx), "count": int(count), "pct": round(int(count) / total * 100, 1)}
        for idx, count in counts.items()
    ]


def _sample(value) -> object:
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return jsonable(value)
    if isinstance(value, (np.integer, np.floating)):
        return jsonable(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    return str(value)[:80]


def _friendly_dtype(sem: dict, s: pd.Series) -> str:
    if sem["role"] == "time":
        return "date"
    if sem["semantic"] == "boolean":
        return "boolean"
    if sem["semantic"] in {"count"}:
        return "integer"
    if sem["semantic"] in {"currency", "percentage", "number"}:
        return "decimal"
    if sem["semantic"] in {"id", "email", "phone", "uuid", "ssn", "ip_address", "credit_card"}:
        return "text"
    return "text"


def _round(v):
    if isinstance(v, float):
        if not np.isfinite(v):
            return None
        return round(v, 4)
    return v
