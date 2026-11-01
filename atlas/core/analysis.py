"""Automated insight discovery.

Atlas ranks candidate findings by effect size, statistical evidence and sample
support, then diversifies across finding types. Each insight ships with the
numbers behind it and a chart spec the UI can render, so nothing is a black box.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np
import pandas as pd

from . import stats
from .semantics import is_measure, pretty
from .util import compact, pct, pretty_period

MAX_INSIGHTS = 9


def build_insights(df: pd.DataFrame, profile: dict) -> list[dict]:
    measures = [c for c in profile["columns"] if is_measure(c)]
    measures.sort(key=lambda c: {"currency": 0, "count": 1, "number": 2, "percentage": 3}.get(c["semantic"], 4))
    dims = [
        c for c in profile["columns"]
        if c["role"] == "dimension" and c["semantic"] not in {"date", "datetime"} and 2 <= c["distinct"] <= 14
    ]
    dims = _dedupe_dimensions(df, dims)
    date_col = (profile.get("time") or {}).get("column")

    candidates: list[dict] = []
    try:
        candidates += _correlation_insights(df, profile, measures)
    except Exception:
        pass
    try:
        candidates += _driver_insights(df, dims, measures)
    except Exception:
        pass
    try:
        candidates += _association_insights(df, dims)
    except Exception:
        pass
    try:
        candidates += _efficiency_insights(df, dims, measures)
    except Exception:
        pass
    try:
        candidates += _concentration_insights(df, dims, measures)
    except Exception:
        pass
    if date_col:
        try:
            candidates += _trend_insights(df, date_col, measures)
            candidates += _anomaly_insights(df, date_col, measures)
        except Exception:
            pass

    candidates = [c for c in candidates if c and c.get("score") and c["score"] >= 30]
    candidates.sort(key=lambda c: -c["score"])
    out: list[dict] = []
    per_kind: dict[str, int] = {}
    used_pairs: set[frozenset] = set()
    driver_measures: set[str] = set()
    corr_cols: set[str] = set()
    trend_measures: set[str] = set()
    anomaly_measures: set[str] = set()
    for cand in candidates:
        kind = cand["kind"]
        limit = 3 if kind in {"driver", "association"} else 1 if kind == "efficiency" else 2
        if per_kind.get(kind, 0) >= limit:
            continue
        cols = cand.get("columns", [])
        pair = frozenset(cols[:2])
        if kind == "driver":
            dim, measure = cols[0], cols[1]
            if measure in driver_measures:
                continue
        if kind == "correlation":
            if any(c in corr_cols for c in cols[:2]):
                continue
        if kind == "trend" and cols[1] in trend_measures:
            continue
        if kind == "anomaly" and cols[1] in anomaly_measures:
            continue
        if pair and pair in used_pairs and kind in {"driver", "association", "correlation"}:
            continue
        out.append(cand)
        per_kind[kind] = per_kind.get(kind, 0) + 1
        if kind == "driver":
            driver_measures.add(cols[1])
        elif kind == "correlation":
            corr_cols.update(cols[:2])
        elif kind == "trend":
            trend_measures.add(cols[1])
        elif kind == "anomaly":
            anomaly_measures.add(cols[1])
        if pair:
            used_pairs.add(pair)
        if len(out) >= MAX_INSIGHTS:
            break
    return out


# --------------------------------------------------------------------------- #
# Correlation
# --------------------------------------------------------------------------- #
def _dedupe_dimensions(df: pd.DataFrame, dims: list[dict]) -> list[dict]:
    """Drop near-duplicate dimensions (e.g. plan is a 1:1 mapping of segment)."""
    kept: list[dict] = []
    for dim in dims:
        duplicate = False
        for other in kept:
            sub = df[[dim["name"], other["name"]]].dropna()
            if len(sub) < 60:
                continue
            table = pd.crosstab(sub[dim["name"]].astype(str), sub[other["name"]].astype(str))
            if table.shape[0] < 2 or table.shape[1] < 2:
                continue
            if (stats.cramers_v(table.to_numpy()).get("v") or 0.0) >= 0.95:
                duplicate = True
                break
        if not duplicate:
            kept.append(dim)
    return kept


def _correlation_insights(df: pd.DataFrame, profile: dict, measures: list[dict]) -> list[dict]:
    cols = [c for c in measures if c["semantic"] in {"currency", "count", "number", "percentage"}][:10]
    cols = [c for c in cols if c.get("stats") and (c["stats"].get("std") or 0) > 0]
    if len(cols) < 2:
        return []
    names = [c["name"] for c in cols]
    sub = df[names].apply(pd.to_numeric, errors="coerce")
    if len(sub) > 80_000:
        sub = sub.sample(80_000, random_state=7)
    by_name = {c["name"]: c for c in cols}
    out: list[dict] = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            pair = sub[[a, b]].dropna()
            if len(pair) < 30:
                continue
            res = stats.pearson(pair[a], pair[b])
            r = res.get("r")
            if r is None or abs(r) < 0.45:
                continue
            rho = stats.spearman(pair[a], pair[b]).get("rho")
            strength = "strong" if abs(r) >= 0.7 else "moderate"
            a_l, b_l = pretty(a), pretty(b)
            plural = a_l.lower().endswith("s") and not a_l.isupper()
            if r > 0:
                direction = "rise with" if plural else "rises with"
            else:
                direction = "move inversely with" if plural else "moves inversely with"
            n = res["n"]
            p_val = res.get("p")
            p_txt = "< 0.001" if p_val is not None and p_val < 0.001 else f"= {p_val:.3f}"
            score = min(94.0, abs(r) * 78 + min(12.0, math.log10(max(10, n)) * 3) + (5 if "currency" in {by_name[a]["semantic"], by_name[b]["semantic"]} else 0))
            include_rho = rho is not None and abs(rho - r) < 0.35
            detail = (
                f"{a_l} {direction} {b_l}: Pearson r = {r:.2f} across {n:,} complete rows "
                f"(p {p_txt})."
                + (f" Spearman ρ = {rho:.2f}, so the relationship is not driven by outliers." if include_rho else "")
                + " Association only — not proof of causation."
            )
            points = [
                [float(x), float(y)]
                for x, y in pair.sample(min(280, len(pair)), random_state=3).itertuples(index=False)
            ]
            out.append({
                "id": _id("corr", a, b),
                "kind": "correlation",
                "title": f"{a_l} {direction} {b_l}",
                "detail": detail,
                "score": round(score, 1),
                "confidence": "high" if n >= 500 and abs(r) >= 0.6 else "medium",
                "columns": [a, b],
                "stats": {"r": round(r, 3), "rho": round(rho, 3) if rho is not None else None, "p": res.get("p"), "n": n},
                "chart": {
                    "type": "scatter",
                    "points": points,
                    "x_label": a_l,
                    "y_label": b_l,
                    "x_format": by_name[a]["semantic"],
                    "y_format": by_name[b]["semantic"],
                },
            })
    out.sort(key=lambda x: -x["score"])
    return out[:4]


# --------------------------------------------------------------------------- #
# Group differences
# --------------------------------------------------------------------------- #
def _driver_insights(df: pd.DataFrame, dims: list[dict], measures: list[dict]) -> list[dict]:
    if not dims or not measures:
        return []
    measures = [m for m in measures if m["semantic"] in {"currency", "percentage", "number", "count"}][:5]
    out: list[dict] = []
    for dim in dims[:6]:
        dname = dim["name"]
        dim_series = df[dname].astype(str).str.strip()
        dim_candidates: list[tuple[int, dict]] = []
        for measure in measures:
            mname = measure["name"]
            values = pd.to_numeric(df[mname], errors="coerce")
            frame = pd.DataFrame({"_dim": dim_series, "_v": values}).dropna()
            frame = frame[frame["_dim"].str.len() > 0]
            if len(frame) < 50:
                continue
            groups, labels = [], []
            for label, grp in frame.groupby("_dim", sort=False):
                if len(grp) < 15:
                    continue
                groups.append(grp["_v"].to_numpy())
                labels.append(str(label))
            if len(groups) < 2:
                continue
            all_means = [float(np.mean(g)) for g in groups]
            eta = stats.eta_squared(groups)
            if eta < 0.06:
                continue
            p = stats.welch_anova(groups).get("p")
            if p is not None and p > 0.01:
                continue
            order = np.argsort(all_means)[::-1]
            top_i, bottom_i = int(order[0]), int(order[-1])
            top_mean, bottom_mean = all_means[top_i], all_means[bottom_i]
            ratio = top_mean / bottom_mean if bottom_mean > 0 else None
            measure_label = pretty(mname)
            fmt = measure["semantic"]
            score = min(95.0, eta * 100 + (6 if p is not None and p < 0.001 else 2) + min(6.0, math.log10(len(frame)) * 1.5) + (10 if fmt == "currency" else 0))
            detail = (
                f"{labels[top_i]} averages {_fmt(top_mean, fmt)} per row versus "
                f"{_fmt(bottom_mean, fmt)} for {labels[bottom_i]}"
                + (f" — a {ratio:.1f}× gap" if ratio else "")
                + f". {pretty(dname)} explains {pct(eta, 0)} of the variation in {measure_label} "
                f"(η² = {eta:.2f}, Welch p {'< 0.001' if p is not None and p < 0.001 else f'= {p:.3f}'})."
            )
            dim_candidates.append((1 if fmt == "currency" else 0, {
                "id": _id("driver", dname, mname),
                "kind": "driver",
                "title": f"{pretty(dname)} is the strongest driver of {measure_label}",
                "detail": detail,
                "score": round(score, 1),
                "confidence": "high" if eta >= 0.14 and len(frame) >= 200 else "medium",
                "columns": [dname, mname],
                "stats": {"eta2": round(eta, 3), "p": p, "top": labels[top_i], "bottom": labels[bottom_i], "ratio": round(ratio, 2) if ratio else None},
                "chart": {
                    "type": "bar",
                    "labels": labels,
                    "values": [round(v, 2) for v in all_means],
                    "label": f"Average {measure_label}",
                    "value_format": fmt,
                },
            }))
        dim_candidates.sort(key=lambda item: (item[0], item[1]["score"]), reverse=True)
        out.extend(item[1] for item in dim_candidates[:2])
    out.sort(key=lambda x: -x["score"])
    return out


# --------------------------------------------------------------------------- #
# Categorical association
# --------------------------------------------------------------------------- #
def _association_insights(df: pd.DataFrame, dims: list[dict]) -> list[dict]:
    """Detect category-to-category relationships (e.g. overtime ↔ attrition)."""
    from itertools import combinations

    candidates = [d for d in dims if d["distinct"] <= 10][:7]
    out: list[dict] = []
    for a, b in combinations(candidates, 2):
        if min(a["distinct"], b["distinct"]) > 4 or max(a["distinct"], b["distinct"]) > 8:
            continue
        sub = df[[a["name"], b["name"]]].dropna()
        if len(sub) < 100:
            continue
        left = sub[a["name"]].astype(str).str.strip()
        right = sub[b["name"]].astype(str).str.strip()
        table = pd.crosstab(left, right)
        if table.shape[0] < 2 or table.shape[1] < 2 or table.size > 144:
            continue
        res = stats.cramers_v(table.to_numpy())
        v = res.get("v") or 0.0
        p = res.get("p")
        if v < 0.18 or v > 0.97 or (p is not None and p > 0.01):
            continue

        if a["semantic"] == "boolean" and b["semantic"] == "boolean":
            a_rate = _truthy(sub[a["name"]]).mean()
            b_rate = _truthy(sub[b["name"]]).mean()
            a_out, b_out = _is_outcome(a["name"]), _is_outcome(b["name"])
            if a_out != b_out:
                outcome, other = (a, b) if a_out else (b, a)
            else:
                outcome, other = (a, b) if a_rate <= b_rate else (b, a)
        elif a["semantic"] == "boolean":
            outcome, other = a, b
        elif b["semantic"] == "boolean":
            outcome, other = b, a
        else:
            outcome, other = (a, b) if a["distinct"] <= b["distinct"] else (b, a)

        ocol, xcol = outcome["name"], other["name"]
        xlabels = sub[xcol].astype(str).str.strip()
        if outcome["semantic"] == "boolean":
            event = sub[ocol].astype(str).str.lower().isin(["true", "1", "yes"])
            event_label = pretty(ocol)
        else:
            counts = sub[ocol].astype(str).value_counts()
            positive = counts.index[-1]
            event = sub[ocol].astype(str) == positive
            event_label = f"{pretty(ocol)} = {_label(positive)}"
        rates = event.groupby(xlabels).mean().sort_values(ascending=False)
        if len(rates) < 2:
            continue
        top_group, bottom_group = str(rates.index[0]), str(rates.index[-1])
        top_rate, bottom_rate = float(rates.iloc[0]), float(rates.iloc[-1])
        if top_rate - bottom_rate < 0.05:
            continue
        detail = (
            f"{event_label} occurs {pct(top_rate, 1)} of the time for {pretty(xcol).lower()} = "
            f"{_label(top_group)}, versus {pct(bottom_rate, 1)} for {_label(bottom_group)} "
            f"(Cramér's V = {v:.2f}, p {'< 0.001' if p is not None and p < 0.001 else f'= {p:.3f}'}, "
            f"n = {len(sub):,})."
        )
        strength = "strongly" if v >= 0.35 else "moderately" if v >= 0.2 else "mildly"
        out.append({
            "id": _id("assoc", a["name"], b["name"]),
            "kind": "association",
            "title": f"{pretty(xcol)} is {strength} associated with {pretty(ocol).lower()}",
            "detail": detail,
            "score": round(min(92.0, 52 + v * 88), 1),
            "confidence": "high" if v >= 0.3 and len(sub) >= 300 else "medium",
            "columns": [xcol, ocol],
            "stats": {"v": round(v, 3), "p": p, "n": len(sub), "top_rate": top_rate, "bottom_rate": bottom_rate},
            "chart": {
                "type": "bar",
                "labels": [_label(str(i)) for i in rates.index],
                "values": [round(float(r) * 100, 2) for r in rates.tolist()],
                "label": event_label,
                "value_format": "percent_points",
            },
        })
    out.sort(key=lambda x: -x["score"])
    return out[:3]


# --------------------------------------------------------------------------- #
# Spend efficiency
# --------------------------------------------------------------------------- #
REVENUE_HINTS = {"revenue", "sales", "gmv", "turnover", "income", "bookings"}
SPEND_HINTS = {"spend", "cost", "budget", "investment", "adspend", "marketing"}
OUTCOME_HINTS = {
    "attrition", "churn", "churned", "converted", "conversion", "retained", "active",
    "left", "default", "fraud", "purchased", "subscribed", "upgraded", "clicked",
    "responded", "cancelled", "renewed",
}


def _has(name: str, hints: set[str]) -> bool:
    import re

    return bool(set(re.split(r"[^a-z0-9]+", str(name).lower())) & hints)


def _is_outcome(name: str) -> bool:
    return _has(name, OUTCOME_HINTS)


def _efficiency_insights(df: pd.DataFrame, dims: list[dict], measures: list[dict]) -> list[dict]:
    currencies = [m for m in measures if m["semantic"] == "currency"]
    revenue = next((m for m in currencies if _has(m["name"], REVENUE_HINTS)), None)
    spend = next((m for m in currencies if _has(m["name"], SPEND_HINTS) and m is not revenue), None)
    if not revenue or not spend or not dims:
        return []
    out: list[dict] = []
    for dim in dims[:4]:
        frame = pd.DataFrame({
            "_d": df[dim["name"]].astype(str).str.strip(),
            "_r": pd.to_numeric(df[revenue["name"]], errors="coerce"),
            "_s": pd.to_numeric(df[spend["name"]], errors="coerce"),
        }).dropna()
        grouped = frame.groupby("_d")[["_r", "_s"]].sum()
        grouped = grouped[grouped["_s"] > 0].sort_values("_r", ascending=True)
        if len(grouped) < 2:
            continue
        reliability = grouped[grouped["_s"] >= grouped["_s"].median() * 0.5]
        if len(reliability) >= 2:
            grouped = reliability
        ratios = (grouped["_r"] / grouped["_s"]).sort_values(ascending=False)
        top_label, bottom_label = str(ratios.index[0]), str(ratios.index[-1])
        top_ratio, bottom_ratio = float(ratios.iloc[0]), float(ratios.iloc[-1])
        if bottom_ratio <= 0:
            continue
        spread = top_ratio / bottom_ratio
        if spread < 1.3:
            continue
        total_spend = float(grouped["_s"].sum())
        total_revenue = float(grouped["_r"].sum())
        out.append({
            "id": _id("efficiency", dim["name"], revenue["name"], spend["name"]),
            "kind": "efficiency",
            "title": f"{pretty(top_label)} has the highest return on {pretty(spend['name']).lower()}",
            "detail": (
                f"{pretty(top_label)} returns ${top_ratio:.2f} of {pretty(revenue['name']).lower()} per $1 of "
                f"{pretty(spend['name']).lower()}, versus ${bottom_ratio:.2f} for {pretty(bottom_label)} "
                f"— a {spread:.1f}× difference. Based on ${compact(total_spend)} spend and "
                f"${compact(total_revenue)} revenue."
            ),
            "score": round(min(93.0, 64 + min(26.0, (spread - 1) * 7)), 1),
            "confidence": "high" if len(frame) >= 100 else "medium",
            "columns": [dim["name"], revenue["name"]],
            "stats": {"ratio_top": round(top_ratio, 3), "ratio_bottom": round(bottom_ratio, 3), "spread": round(spread, 2)},
            "chart": {
                "type": "bar",
                "labels": [str(i) for i in ratios.index],
                "values": [round(float(v), 3) for v in ratios.tolist()],
                "label": f"Revenue per $1 {pretty(spend['name']).lower()}",
                "value_format": "ratio",
            },
        })
    out.sort(key=lambda x: -x["score"])
    return out[:2]


# --------------------------------------------------------------------------- #
# Concentration
# --------------------------------------------------------------------------- #
def _concentration_insights(df: pd.DataFrame, dims: list[dict], measures: list[dict]) -> list[dict]:
    currencies = [m for m in measures if m["semantic"] == "currency"]
    if currencies:
        sums = {m["name"]: float(pd.to_numeric(df[m["name"]], errors="coerce").sum()) for m in currencies}
        measure = max(currencies, key=lambda m: sums.get(m["name"], 0.0))
    else:
        counts = [m for m in measures if m["semantic"] == "count"]
        measure = counts[0] if counts else None
    if not measure or not dims:
        return []
    mname = measure["name"]
    values = pd.to_numeric(df[mname], errors="coerce")
    best = None
    for dim in dims[:6]:
        if dim["semantic"] not in {"category", "country", "boolean"}:
            continue
        if dim["semantic"] == "boolean" or dim["distinct"] < 3:
            continue
        dname = dim["name"]
        frame = pd.DataFrame({"_d": df[dname].astype(str).str.strip(), "_v": values}).dropna()
        if len(frame) < 30:
            continue
        totals = frame.groupby("_d")["_v"].sum().sort_values(ascending=False)
        if len(totals) < 2:
            continue
        total = float(totals.sum())
        if total <= 0:
            continue
        share = float(totals.iloc[0]) / total
        if share < 0.35:
            continue
        candidate = (share, dim, totals, total, len(frame))
        if best is None or candidate[0] > best[0]:
            best = candidate
    if not best:
        return []
    share, dim, totals, total, n = best
    top_label = str(totals.index[0])
    detail = (
        f"{top_label} contributes {_fmt(float(totals.iloc[0]), measure['semantic'])} of "
        f"{_fmt(total, measure['semantic'])} total {pretty(mname)} ({pct(share, 0)}). "
        f"The top two categories account for {pct(float(totals.iloc[:2].sum()) / total, 0)}."
    )
    labels = [str(v) for v in totals.index]
    return [{
        "id": _id("concentration", dim["name"], mname),
        "kind": "concentration",
        "title": f"{top_label} concentrates {pct(share, 0)} of total {pretty(mname)}",
        "detail": detail,
        "score": round(46 + share * 45, 1),
        "confidence": "high" if n >= 100 else "medium",
        "columns": [dim["name"], mname],
        "stats": {"share": round(share, 3), "top": top_label, "total": total},
        "chart": {
            "type": "bar",
            "labels": labels,
            "values": [round(float(v), 2) for v in totals.tolist()],
            "label": f"Total {pretty(mname)}",
            "value_format": measure["semantic"],
        },
    }]


# --------------------------------------------------------------------------- #
# Trend
# --------------------------------------------------------------------------- #
def _trend_insights(df: pd.DataFrame, date_col: str, measures: list[dict]) -> list[dict]:
    dates = pd.to_datetime(df[date_col], errors="coerce")
    if dates.notna().sum() < 30:
        return []
    out: list[dict] = []
    candidates = [m for m in measures if m["semantic"] in {"currency", "count", "number"}][:6]
    for measure in candidates:
        mname = measure["name"]
        values = pd.to_numeric(df[mname], errors="coerce")
        frame = pd.DataFrame({"d": dates, "v": values}).dropna()
        if len(frame) < 30:
            continue
        frame["period"] = frame["d"].dt.to_period("M")
        day_counts = frame.groupby("period")["d"].nunique()
        if len(day_counts) < 6:
            continue
        # Drop partial first/last months: a 1-day October would fake a 95% collapse.
        median_days = float(day_counts.median())
        complete = day_counts[day_counts >= max(2.0, median_days * 0.8)].index
        frame = frame[frame["period"].isin(complete)]
        agg = _agg_for(mname, measure["semantic"])
        monthly = frame.groupby("period")["v"].agg(agg)
        if len(monthly) < 6:
            continue
        y = monthly.to_numpy(dtype=float)
        trend = stats.ols_trend(y)
        r2 = trend.get("r2") or 0
        first, last = float(y[0]), float(y[-1])
        growth = (last - first) / abs(first) if first else None
        if r2 < 0.18 and (growth is None or abs(growth) < 0.08):
            continue
        if r2 >= 0.5:
            score = r2 * 58 + min(30.0, abs(growth or 0) * 32) + 8
        else:
            score = r2 * 45 + min(24.0, abs(growth or 0) * 22)
        if measure["semantic"] == "currency":
            score += 10
        direction = "climbed" if (growth or 0) > 0 else "fell"
        if abs(growth or 0) < 0.02:
            direction = "held steady"
        labels = [str(p) for p in monthly.index]
        first_label = pretty_period(labels[0], "month")
        last_label = pretty_period(labels[-1], "month")
        agg_label = "average" if agg == "mean" else "total"
        detail = (
            f"Monthly {agg_label} {pretty(mname).lower()} {direction} from {_fmt(first, measure['semantic'])} in "
            f"{first_label} to {_fmt(last, measure['semantic'])} in {last_label} "
            f"({'+' if (growth or 0) >= 0 else ''}{pct(growth, 1)}), with a linear fit of R² = {r2:.2f}. "
            f"{len(monthly)} complete months analysed."
        )
        out.append({
            "id": _id("trend", mname, date_col),
            "kind": "trend",
            "title": f"{pretty(mname)} {direction} {pct(abs(growth) if growth is not None else None, 0)} over {len(monthly)} months",
            "detail": detail,
            "score": round(min(94.0, score), 1),
            "confidence": "high" if r2 >= 0.5 else "medium",
            "columns": [date_col, mname],
            "stats": {"growth": growth, "r2": r2, "first": first, "last": last, "periods": len(monthly), "agg": agg},
            "chart": {
                "type": "line",
                "labels": labels,
                "values": [round(float(v), 2) for v in y.tolist()],
                "label": f"{'Average' if agg == 'mean' else 'Total'} {pretty(mname)}",
                "value_format": measure["semantic"],
            },
        })
    out.sort(key=lambda x: -x["score"])
    return out[:3]


# --------------------------------------------------------------------------- #
# Anomalies
# --------------------------------------------------------------------------- #
def _anomaly_insights(df: pd.DataFrame, date_col: str, measures: list[dict]) -> list[dict]:
    dates = pd.to_datetime(df[date_col], errors="coerce")
    out: list[dict] = []
    for measure in measures[:5]:
        if measure["semantic"] not in {"currency", "count", "percentage", "number"}:
            continue
        mname = measure["name"]
        values = pd.to_numeric(df[mname], errors="coerce")
        frame = pd.DataFrame({"d": dates, "v": values}).dropna()
        if len(frame) < 60:
            continue
        agg = _agg_for(mname, measure["semantic"])
        daily = frame.groupby(frame["d"].dt.floor("D"))["v"].agg(agg)
        if len(daily) < 30:
            continue
        arr = daily.to_numpy(dtype=float)
        z = stats.robust_z(arr)
        flags = np.where(np.abs(z) > 3.5)[0]
        if len(flags) == 0:
            continue
        baseline = float(np.median(arr))
        peak_i = int(flags[np.argmax(np.abs(z[flags]))])
        peak = float(arr[peak_i])
        multiple = peak / baseline if baseline else None
        peak_date = daily.index[peak_i].to_pydatetime()
        zmax = float(abs(z[peak_i]))
        score = min(96.0, 40 + zmax * 9)
        direction = "spiked" if peak > baseline else "dropped"
        detail = (
            f"On {peak_date.strftime('%d %b %Y')}, {pretty(mname).lower()} {direction} to "
            f"{_fmt(peak, measure['semantic'])} versus a median of {_fmt(baseline, measure['semantic'])}"
            + (f" ({multiple:.1f}× typical)" if multiple else "")
            + f" — a robust z-score of {zmax:.1f}. {len(flags)} "
            + ("day" if len(flags) == 1 else "days")
            + " breached the 3.5 threshold."
        )
        labels = [d.strftime("%Y-%m-%d") for d in daily.index]
        anomaly_points = [
            {"index": int(i), "label": labels[i], "value": round(float(arr[i]), 2), "z": round(float(z[i]), 2)}
            for i in flags[:12]
        ]
        out.append({
            "id": _id("anomaly", mname, date_col),
            "kind": "anomaly",
            "title": f"{pretty(mname)} {direction} to {multiple:.1f}× typical in {peak_date.strftime('%B %Y')}" if multiple else f"{pretty(mname)} anomaly in {peak_date.strftime('%B %Y')}",
            "detail": detail,
            "score": round(score, 1),
            "confidence": "high" if zmax >= 5 else "medium",
            "columns": [date_col, mname],
            "stats": {"peak": peak, "baseline": baseline, "multiple": multiple, "z": zmax, "date": labels[peak_i], "flagged_days": len(flags)},
            "chart": {
                "type": "line",
                "labels": labels,
                "values": [round(float(v), 2) for v in arr.tolist()],
                "label": pretty(mname),
                "value_format": measure["semantic"],
                "anomalies": anomaly_points,
            },
        })
    out.sort(key=lambda x: -x["score"])
    return out[:3]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
FLOW_HINTS = {
    "revenue", "sales", "tickets", "signups", "clicks", "conversions", "impressions",
    "leads", "trials", "orders", "units", "transactions", "visits", "spend", "cost",
}


def _agg_for(name: str, semantic: str | None) -> str:
    """Stock metrics (seats, customers) average; flow metrics (revenue, tickets) sum."""
    if semantic == "currency":
        return "sum"
    tokens = set(str(name).lower().replace("-", "_").split("_"))
    return "sum" if tokens & FLOW_HINTS else "mean"


def _truthy(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "yes", "y", "t"])


def _label(value: str) -> str:
    return {"True": "Yes", "False": "No", "true": "Yes", "false": "No"}.get(str(value), str(value))


def _fmt(value: float | None, fmt: str | None) -> str:
    if value is None:
        return "—"
    if fmt == "currency":
        return "$" + compact(value)
    if fmt == "percentage":
        return f"{value:.1f}%"
    return compact(value)


def _id(*parts: str) -> str:
    return "ins_" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]
