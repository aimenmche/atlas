"""Comparison, cohort, relationship and significance tests."""
from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.core import stats
from atlas.core.cohort import cohort_retention
from atlas.core.compare import period_comparison
from atlas.core.relationships import correlation_matrix, lag_analysis


def _monthly() -> pd.DataFrame:
    rows = []
    values = {"EMEA": [100, 110, 120, 130, 140, 150], "APAC": [80, 82, 84, 86, 88, 90]}
    for month, (emea, apac) in enumerate(zip(values["EMEA"], values["APAC"]), start=1):
        day = (pd.Timestamp(year=2025, month=month, day=1) + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
        for region, value in (("EMEA", emea), ("APAC", apac)):
            rows.append({"date": day, "region": region, "revenue": value})
    return pd.DataFrame(rows)


def test_period_comparison_counts_complete_months_and_reconciles():
    result = period_comparison(_monthly(), "date", "revenue", grain="month", dimension="region")
    assert result["current_period"] == "Jun 2025"
    assert result["previous_period"] == "May 2025"
    assert result["current"] == 240
    assert result["previous"] == 228
    assert result["delta"] == 12
    assert result["direction"] == "up"
    assert round(result["change_pct"], 2) == 5.26
    deltas = {row["label"]: row["delta"] for row in result["contributions"]}
    assert deltas["EMEA"] == 10
    assert deltas["APAC"] == 2
    assert sum(deltas.values()) == result["delta"]
    assert result["waterfall"][0]["kind"] == "start"
    assert result["waterfall"][-1]["kind"] == "end"
    assert "revenue" in result["narrative"].lower()


def test_period_comparison_drops_partial_period():
    frame = _monthly()
    extra = pd.DataFrame({"date": ["2025-07-01"], "region": ["EMEA"], "revenue": [999]})
    result = period_comparison(pd.concat([frame, extra], ignore_index=True), "date", "revenue")
    assert result["current_period"] == "Jun 2025"


def test_cohort_retention_matrix():
    frame = pd.DataFrame({
        "customer": ["a", "a", "a", "b", "b", "c", "b", "c"],
        "date": [
            "2025-01-03", "2025-02-04", "2025-03-05",
            "2025-01-07", "2025-03-08",
            "2025-02-11", "2025-04-03", "2025-04-04",
        ],
    })
    result = cohort_retention(frame, "customer", "date", grain="month", periods=4)
    assert result["headline_retention"] is not None
    assert len(result["cohorts"]) == 2
    assert result["cohorts"][0]["size"] == 2
    assert result["cohorts"][0]["values"][0] == 100.0
    # January cohort: both customers return in March (index 2), one in April.
    assert result["cohorts"][0]["values"][1] == 50.0
    assert result["cohorts"][0]["values"][2] == 100.0
    assert result["cohorts"][0]["values"][3] == 50.0


def test_correlation_matrix_is_symmetric():
    frame = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [2, 4, 6, 8, 10], "c": [5, 4, 3, 2, 1]})
    result = correlation_matrix(frame, ["a", "b", "c"])
    assert result["matrix"][0][0] == 1.0
    assert result["matrix"][0][1] == 1.0
    assert result["matrix"][0][2] == -1.0
    assert result["matrix"][1][0] == result["matrix"][0][1]


def test_lag_analysis_recovers_a_one_period_lead():
    periods = pd.date_range("2024-01-01", periods=24, freq="MS")
    x = np.sin(np.arange(24) / 2.0) * 20 + 100
    y = np.concatenate([[0.0], x[:-1]]) + 5
    frame = pd.DataFrame({"date": periods, "x": x, "y": y})
    result = lag_analysis(frame, "date", "x", "y", grain="month", max_lag=4)
    assert result["best_lag"] == 1
    assert result["best_r"] is not None and result["best_r"] > 0.9
    assert result["lead"]["column"] == "x"
    assert result["lead"]["lag"] == 1


def test_welch_t_detects_separation_and_effect_size():
    rng = np.random.default_rng(7)
    a = rng.normal(12, 1.0, 200)
    b = rng.normal(10, 1.0, 200)
    result = stats.welch_t(a, b)
    assert result["p"] < 1e-6
    assert result["diff"] > 1.5
    assert result["cohen_d"] > 1.5
    assert result["ci_low"] < result["ci_high"]
    same = stats.welch_t(a, a)
    assert same["t"] == 0.0
