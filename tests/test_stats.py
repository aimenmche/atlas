"""Numerical primitives must be correct without SciPy.

Each test checks a closed-form value or an invariant that would catch a broken
special-function implementation.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from atlas.core import stats


def test_normal_tail_matches_closed_form():
    assert stats.norm_sf(0.0) == pytest.approx(0.5, abs=1e-9)
    assert stats.norm_sf(1.96) == pytest.approx(0.0249979, abs=2e-6)


def test_t_and_f_pvalues_hit_known_critical_values():
    # Two-sided 5% critical values from standard tables.
    assert stats.t_pvalue(2.228, 10) == pytest.approx(0.05, abs=5e-4)
    assert stats.t_pvalue(0.0, 10) == pytest.approx(1.0, abs=1e-9)
    assert stats.f_pvalue(4.9646, 1, 10) == pytest.approx(0.05, abs=1e-3)
    assert stats.chi2_pvalue(3.8415, 1) == pytest.approx(0.05, abs=5e-4)


def test_describe_and_histogram():
    summary = stats.describe([1, 2, 3, 4, 5])
    assert summary["count"] == 5
    assert summary["mean"] == pytest.approx(3.0)
    assert summary["median"] == pytest.approx(3.0)
    assert summary["min"] == 1 and summary["max"] == 5
    assert summary["sum"] == 15

    hist = stats.histogram([1, 1, 2, 3, 3, 3])
    assert sum(hist["counts"]) == 6
    assert len(hist["labels"]) == len(hist["edges"])


def test_pearson_and_spearman_on_monotonic_data():
    x = np.arange(1, 30, dtype=float)
    y = 2 * x + 3
    pear = stats.pearson(x, y)
    assert pear["r"] == pytest.approx(1.0)
    assert pear["p"] == pytest.approx(0.0)
    assert pear["n"] == 29

    curved = x ** 2
    spear = stats.spearman(x, curved)
    assert spear["rho"] == pytest.approx(1.0)


def test_welch_anova_separates_shifted_groups():
    rng = np.random.default_rng(42)
    a = rng.normal(10, 1, 80)
    b = rng.normal(10, 1, 80)
    c = rng.normal(14, 1, 80)
    shifted = stats.welch_anova([a, b, c])
    assert shifted["F"] > 100
    assert shifted["p"] < 1e-12
    assert 0 < shifted["df2"] < 240

    same = stats.welch_anova([a, b])
    assert same["p"] > 0.01


def test_eta_squared_and_cramers_v():
    groups = [np.array([1.0, 1.1, 0.9]), np.array([5.0, 5.1, 4.9])]
    assert stats.eta_squared(groups) > 0.95

    # Perfectly dependent 2x2 table.
    table = np.array([[10, 0], [0, 10]])
    result = stats.cramers_v(table)
    assert result["v"] == pytest.approx(1.0)
    assert result["p"] < 0.001

    independent = np.array([[10, 10], [10, 10]])
    assert stats.cramers_v(independent)["p"] == pytest.approx(1.0, abs=1e-9)


def test_ols_trend_recovers_exact_line():
    x = np.arange(20, dtype=float)
    y = 7.5 + 2.25 * x
    trend = stats.ols_trend(y)
    assert trend["slope"] == pytest.approx(2.25)
    assert trend["intercept"] == pytest.approx(7.5)
    assert trend["r2"] == pytest.approx(1.0)


def test_autocorr_edges():
    assert stats.autocorr([1.0] * 10, 1) == 0.0
    sine = [math.sin(i / 2) for i in range(200)]
    lagged = stats.autocorr(sine, 1)
    assert lagged > 0.5
