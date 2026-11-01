"""Data-quality scoring: completeness, uniqueness, consistency, validity.

The output is intentionally explainable — every point lost is tied to an issue
with a severity, an affected column and a concrete remediation.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .semantics import is_measure
from .util import pretty


def build_quality(df: pd.DataFrame, columns: list[dict]) -> dict:
    rows = len(df)
    cols = len(df.columns)
    total_cells = max(1, rows * cols)

    missing_cells = int(df.isna().sum().sum())
    completeness = 1.0 - missing_cells / total_cells

    dup_rows = int(df.duplicated().sum())
    uniqueness = 1.0 - (dup_rows / rows if rows else 0.0)

    consistency, inconsistency_issues = _consistency(df, columns)
    validity, validity_issues = _validity(df, columns)

    score = 100.0 * (
        0.40 * completeness + 0.15 * uniqueness + 0.20 * consistency + 0.25 * validity
    )
    score = round(max(0.0, min(100.0, score)), 1)
    grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"

    issues: list[dict] = []
    for col in columns:
        name = col["name"]
        label = pretty(name)
        miss = col["null_pct"]
        if miss >= 20:
            issues.append(_issue("high", "Missing data", f"{label} is {miss:.0f}% empty — conclusions about it are unreliable.", name, "completeness", 12))
        elif miss >= 5:
            issues.append(_issue("medium", "Missing data", f"{label} is {miss:.1f}% empty; Atlas excludes nulls from calculations.", name, "completeness", 6))
        elif miss > 0:
            issues.append(_issue("low", "Sparse nulls", f"{label} has {miss:.1f}% missing values.", name, "completeness", 2))
        if col.get("pii"):
            issues.append(_issue("high", "Personal data", f"{label} looks like PII ({col['semantic']}). Mask it before sharing reports.", name, "privacy", 0))
        if col.get("flags") and "constant" in col["flags"]:
            issues.append(_issue("low", "Constant column", f"{label} has a single value and adds no analytical signal.", name, "consistency", 3))
        out_pct = col.get("outlier_pct") or 0
        if col.get("role") == "measure" and out_pct >= 2:
            issues.append(_issue("medium", "Outliers", f"{label} has {out_pct:.1f}% extreme values (robust z > 3.5).", name, "validity", 5))
        elif col.get("role") == "measure" and out_pct > 0:
            issues.append(_issue("low", "Outliers", f"{label} has {out_pct:.1f}% extreme values.", name, "validity", 2))
        if col.get("flags") and "high_cardinality" in col["flags"]:
            issues.append(_issue("low", "High cardinality", f"{label} has {col['distinct']:,} distinct values — better as an identifier than a grouping key.", name, "consistency", 0))
        if col.get("invalid_pct") and col["invalid_pct"] > 0:
            issues.append(_issue("high", "Invalid values", f"{label} has {col['invalid_pct']:.1f}% values outside its expected range.", name, "validity", 8))

    if dup_rows > 0:
        pct = dup_rows / rows * 100
        issues.append(_issue(
            "high" if pct > 2 else "medium",
            "Duplicate rows",
            f"{dup_rows:,} exact duplicate rows ({pct:.1f}%) — totals may be overstated.",
            None, "uniqueness", 8 if pct > 2 else 4,
        ))

    issues.extend(inconsistency_issues)
    issues.extend(validity_issues)
    issues.sort(key=lambda i: {"high": 0, "medium": 1, "low": 2}[i["severity"]])

    return {
        "score": score,
        "grade": grade,
        "dimensions": {
            "completeness": round(completeness * 100, 1),
            "uniqueness": round(uniqueness * 100, 1),
            "consistency": round(consistency * 100, 1),
            "validity": round(validity * 100, 1),
        },
        "issues": issues[:24],
        "issue_counts": {
            "high": sum(1 for i in issues if i["severity"] == "high"),
            "medium": sum(1 for i in issues if i["severity"] == "medium"),
            "low": sum(1 for i in issues if i["severity"] == "low"),
        },
        "missing_cells": missing_cells,
        "duplicate_rows": dup_rows,
    }


def _consistency(df: pd.DataFrame, columns: list[dict]) -> tuple[float, list[dict]]:
    """Penalize label drift such as 'EMEA' vs 'emea' vs ' EMEA'."""
    checked = 0
    penalty = 0.0
    issues: list[dict] = []
    for col in columns:
        if col["role"] != "dimension" or col.get("semantic") == "date":
            continue
        series = df[col["name"]].dropna()
        if series.empty or series.nunique() > 100:
            continue
        checked += 1
        as_text = series.astype(str)
        norm = as_text.str.replace(r"\s+", " ", regex=True).str.strip().str.lower()
        variants = int(as_text.nunique() - norm.nunique())
        if variants > 0:
            examples = sorted(set(as_text[norm.duplicated(keep=False)].tolist()), key=len)[:5]
            col["inconsistent_categories"] = examples
            penalty += min(0.5, variants / max(1, as_text.nunique()) * 2)
            issues.append(_issue(
                "medium", "Inconsistent labels",
                f"{pretty(col['name'])} contains {variants} case/whitespace variant(s): {', '.join(examples)}.",
                col["name"], "consistency", 4,
            ))
    score = 1.0 - (penalty / checked if checked else 0.0)
    return max(0.0, score), issues


def _validity(df: pd.DataFrame, columns: list[dict]) -> tuple[float, list[dict]]:
    measures = [c for c in columns if is_measure(c)]
    if not measures:
        return 1.0, []
    penalty = 0.0
    issues: list[dict] = []
    for col in measures:
        series = pd.to_numeric(df[col["name"]], errors="coerce").dropna()
        if series.empty:
            continue
        invalid_ratio = 0.0
        if col["semantic"] == "percentage":
            invalid_ratio = float(((series < 0) | (series > 100)).mean())
        elif col["semantic"] == "count":
            invalid_ratio = float((series < 0).mean())
        col["invalid_pct"] = round(invalid_ratio * 100, 2)
        out_ratio = min(0.5, (col.get("outlier_pct") or 0) / 100.0)
        penalty += min(0.6, invalid_ratio * 4 + out_ratio * 1.5)
        if invalid_ratio > 0.005:
            issues.append(_issue(
                "high", "Out-of-range values",
                f"{pretty(col['name'])} has {invalid_ratio * 100:.1f}% values outside its expected range.",
                col["name"], "validity", 8,
            ))
    return max(0.0, 1.0 - penalty / len(measures)), issues


def _issue(severity: str, title: str, detail: str, column: str | None, category: str, points: int) -> dict:
    return {
        "id": re.sub(r"[^a-z0-9]+", "-", f"{title}-{column or 'dataset'}".lower()).strip("-"),
        "severity": severity,
        "title": title,
        "detail": detail,
        "column": column,
        "category": category,
        "impact_points": points,
    }
