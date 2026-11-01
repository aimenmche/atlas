"""Numerical primitives used across Atlas.

Deliberately dependency-light (NumPy only) and validated in ``tests/test_stats.py``
against closed-form values. Implements the regularized incomplete beta/gamma
functions so p-values are computed without SciPy.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

EPS = 3e-14
TINY = 1e-300


# --------------------------------------------------------------------------- #
# Special functions
# --------------------------------------------------------------------------- #
def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (Numerical Recipes)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < TINY:
        d = TINY
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _gser(a: float, x: float) -> float:
    gln = math.lgamma(a)
    ap = a
    total = 1.0 / a
    delta = total
    for _ in range(1, 500):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * EPS:
            break
    return total * math.exp(-x + a * math.log(x) - gln)


def _gcf(a: float, x: float) -> float:
    gln = math.lgamma(a)
    b = x + 1.0 - a
    c = 1.0 / TINY
    d = 1.0 / b if abs(b) > TINY else 1.0 / TINY
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < TINY:
            d = TINY
        c = b + an / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


def gammaincc(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x)."""
    if x <= 0.0:
        return 1.0
    if x < a + 1.0:
        return max(0.0, 1.0 - _gser(a, x))
    return min(1.0, _gcf(a, x))


def norm_sf(z: float) -> float:
    """P(Z > z) for a standard normal."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def t_pvalue(t: float, df: float) -> float:
    """Two-sided p-value for a t statistic."""
    if not math.isfinite(t) or df <= 0:
        return 1.0
    return betai(df / 2.0, 0.5, df / (df + t * t))


def f_pvalue(f: float, d1: float, d2: float) -> float:
    """Upper-tail p-value for an F statistic."""
    if not math.isfinite(f) or f <= 0 or d1 <= 0 or d2 <= 0:
        return 1.0
    return betai(d2 / 2.0, d1 / 2.0, d2 / (d2 + d1 * f))


def chi2_pvalue(x: float, df: int) -> float:
    if x <= 0 or df <= 0:
        return 1.0
    return gammaincc(df / 2.0, x / 2.0)


# --------------------------------------------------------------------------- #
# Descriptive statistics
# --------------------------------------------------------------------------- #
def finite(values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(list(values) if not isinstance(values, np.ndarray) else values, dtype=float)
    return arr[np.isfinite(arr)]


def mean(values: Sequence[float]) -> float:
    arr = finite(values)
    return float(arr.mean()) if arr.size else float("nan")


def describe(values: Sequence[float]) -> dict:
    """Robust descriptive summary. Returns ``{}`` for empty input."""
    arr = finite(values)
    n = int(arr.size)
    if n == 0:
        return {}
    mean_v = float(arr.mean())
    std_v = float(arr.std(ddof=1)) if n > 1 else 0.0
    q1, med, q3 = (float(v) for v in np.percentile(arr, [25, 50, 75]))
    m2 = float(np.mean((arr - mean_v) ** 2)) or 1e-12
    skew = float(np.mean((arr - mean_v) ** 3) / m2**1.5)
    kurt = float(np.mean((arr - mean_v) ** 4) / m2**2 - 3.0)
    return {
        "count": n,
        "mean": mean_v,
        "std": std_v,
        "min": float(arr.min()),
        "p25": q1,
        "median": med,
        "p75": q3,
        "max": float(arr.max()),
        "sum": float(arr.sum()),
        "range": float(arr.max() - arr.min()),
        "cv": float(std_v / mean_v) if mean_v else None,
        "skew": skew,
        "kurtosis": kurt,
        "iqr": q3 - q1,
    }


def histogram(values: Sequence[float], max_bins: int = 24) -> dict:
    arr = finite(values)
    if arr.size == 0:
        return {"edges": [], "counts": [], "labels": []}
    unique = np.unique(arr)
    if unique.size <= max_bins:
        counts = [int((arr == u).sum()) for u in unique]
        labels = [_compact(float(u)) for u in unique]
        edges = [float(v) for v in unique]
        return {"edges": edges, "counts": counts, "labels": labels}
    bins = int(min(max_bins, max(6, min(30, np.ceil(np.sqrt(arr.size))))))
    counts, edges = np.histogram(arr, bins=bins)
    labels = [_compact(float(edges[i])) for i in range(len(edges) - 1)]
    return {
        "edges": [float(e) for e in edges],
        "counts": [int(c) for c in counts],
        "labels": labels,
    }


def _compact(x: float) -> str:
    ax = abs(x)
    if ax >= 1e9:
        return f"{x / 1e9:.1f}B"
    if ax >= 1e6:
        return f"{x / 1e6:.1f}M"
    if ax >= 1e3:
        return f"{x / 1e3:.1f}K"
    if ax == int(ax):
        return str(int(ax))
    return f"{x:.2f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- #
# Association & hypothesis tests
# --------------------------------------------------------------------------- #
def pearson(x: Sequence[float], y: Sequence[float]) -> dict:
    xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    mask = np.isfinite(xa) & np.isfinite(ya)
    xa, ya = xa[mask], ya[mask]
    n = int(min(xa.size, ya.size))
    if n < 3:
        return {"r": None, "p": None, "n": n}
    if xa.std() == 0 or ya.std() == 0:
        return {"r": 0.0, "p": 1.0, "n": n}
    r = float(np.corrcoef(xa, ya)[0, 1])
    r = max(-1.0, min(1.0, r))
    if abs(r) >= 1.0:
        return {"r": r, "p": 0.0, "n": n}
    t = r * math.sqrt((n - 2) / (1 - r * r))
    return {"r": r, "p": t_pvalue(t, n - 2), "n": n}


def _rankdata(values: np.ndarray) -> np.ndarray:
    """Average ranks, ties handled without SciPy."""
    n = values.size
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(n, dtype=float)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        ranks[order[i : j + 1]] = avg
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> dict:
    xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    mask = np.isfinite(xa) & np.isfinite(ya)
    xa, ya = xa[mask], ya[mask]
    if xa.size < 3:
        return {"rho": None, "p": None, "n": int(xa.size)}
    res = pearson(_rankdata(xa), _rankdata(ya))
    return {"rho": res["r"], "p": res["p"], "n": res["n"]}


def welch_anova(groups: Sequence[Sequence[float]]) -> dict:
    """Welch's ANOVA — robust to unequal variances and group sizes."""
    cleaned = [finite(g) for g in groups]
    cleaned = [g for g in cleaned if g.size >= 2]
    k = len(cleaned)
    if k < 2:
        return {"F": None, "p": None, "df1": None, "df2": None}
    means = np.array([g.mean() for g in cleaned])
    variances = np.array([g.var(ddof=1) for g in cleaned])
    ns = np.array([g.size for g in cleaned], dtype=float)
    variances = np.where(variances <= 0, 1e-12, variances)
    w = ns / variances
    wsum = w.sum()
    if wsum <= 0:
        return {"F": None, "p": None, "df1": None, "df2": None}
    mean_w = float((w * means).sum() / wsum)
    a = float((w * (means - mean_w) ** 2).sum() / (k - 1))
    term = ((1 - w / wsum) ** 2 / (ns - 1)).sum()
    b = 1.0 + (2.0 * (k - 2) / (k * k - 1.0)) * term
    denom = 3.0 * term
    df2 = (k * k - 1.0) / denom if denom > 0 else float(ns.sum() - k)
    f = a / b if b > 0 else 0.0
    return {
        "F": float(f),
        "p": float(f_pvalue(f, k - 1, df2)),
        "df1": k - 1,
        "df2": float(df2),
    }


def eta_squared(groups: Sequence[Sequence[float]]) -> float:
    """Proportion of variance explained by group membership (0..1)."""
    cleaned = [finite(g) for g in groups]
    cleaned = [g for g in cleaned if g.size > 0]
    if len(cleaned) < 2:
        return 0.0
    all_vals = np.concatenate(cleaned)
    grand = all_vals.mean()
    ss_total = float(((all_vals - grand) ** 2).sum())
    if ss_total <= 0:
        return 0.0
    ss_between = sum(g.size * (g.mean() - grand) ** 2 for g in cleaned)
    return float(max(0.0, min(1.0, ss_between / ss_total)))


def cramers_v(table: np.ndarray) -> dict:
    """Cramér's V with a chi-square test of independence."""
    table = np.asarray(table, dtype=float)
    if table.ndim != 2 or table.size == 0:
        return {"v": None, "p": None, "chi2": None, "df": None}
    table = table[table.sum(axis=1) > 0][:, table.sum(axis=0) > 0]
    if table.shape[0] < 2 or table.shape[1] < 2:
        return {"v": 0.0, "p": 1.0, "chi2": 0.0, "df": 0}
    total = table.sum()
    expected = np.outer(table.sum(axis=1), table.sum(axis=0)) / total
    with np.errstate(divide="ignore", invalid="ignore"):
        chi2 = float(np.nansum((table - expected) ** 2 / expected))
    df = (table.shape[0] - 1) * (table.shape[1] - 1)
    v = math.sqrt(chi2 / (total * (min(table.shape) - 1))) if total > 0 else 0.0
    return {
        "v": float(min(1.0, v)),
        "p": float(chi2_pvalue(chi2, df)),
        "chi2": chi2,
        "df": df,
    }


# --------------------------------------------------------------------------- #
# Trend / time series helpers
# --------------------------------------------------------------------------- #
def ols_trend(y: Sequence[float], x: Sequence[float] | None = None) -> dict:
    ya = np.asarray(y, dtype=float)
    mask = np.isfinite(ya)
    ya = ya[mask]
    n = ya.size
    if n < 3:
        return {"slope": None, "intercept": None, "r2": None, "n": n}
    xa = np.asarray(x, dtype=float)[mask] if x is not None else np.arange(n, dtype=float)
    slope, intercept = np.polyfit(xa, ya, 1)
    pred = slope * xa + intercept
    ss_res = float(((ya - pred) ** 2).sum())
    ss_tot = float(((ya - ya.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "r2": float(max(0.0, min(1.0, r2))),
        "n": n,
    }


def autocorr(values: Sequence[float], lag: int) -> float:
    arr = finite(values)
    if arr.size <= lag + 2:
        return 0.0
    a, b = arr[:-lag], arr[lag:]
    if a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def robust_z(values: Sequence[float]) -> np.ndarray:
    """Median/MAD z-scores; falls back to IQR then std when MAD collapses."""
    arr = np.asarray(values, dtype=float)
    arr = np.where(np.isfinite(arr), arr, np.nan)
    med = np.nanmedian(arr)
    mad = np.nanmedian(np.abs(arr - med))
    if mad and mad > 0:
        scale = 1.4826 * mad
    else:
        q1, q3 = np.nanpercentile(arr, [25, 75])
        scale = (q3 - q1) / 1.349 if q3 > q1 else np.nanstd(arr)
    if not scale or not np.isfinite(scale) or scale == 0:
        return np.zeros_like(arr)
    with np.errstate(invalid="ignore"):
        return (arr - med) / scale


def outlier_count(values: Sequence[float], threshold: float = 3.5) -> int:
    z = robust_z(values)
    return int(np.nansum(np.abs(z) > threshold))


def safe_div(a: float, b: float) -> float | None:
    if b is None or b == 0 or not math.isfinite(b):
        return None
    return float(a) / float(b)
