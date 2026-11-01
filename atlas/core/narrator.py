"""Grounded narrative generation.

Every sentence is built from the actual query result. This module also emits
the ``facts`` dictionary used to verify any optional LLM polish, so a language
model can improve prose but cannot smuggle in a new number.
"""
from __future__ import annotations

import math
import re

from . import stats
from .semantics import pretty
from .util import compact, pct, pretty_period


def narrate(question: str, parsed: dict, result: dict, profile: dict) -> dict:
    columns = result.get("columns", [])
    rows = result.get("rows", [])
    chart_type = parsed.get("chart_type", "table")
    fmt = parsed.get("value_format") or "number"
    title = parsed.get("title") or question
    caveats: list[str] = []
    facts: dict = {"title": title, "question": question, "rows_returned": len(rows)}

    if not rows:
        return {
            "narrative": "No rows matched that question. Try removing a filter or checking the column values.",
            "highlights": [],
            "facts": facts,
            "caveats": ["The query returned zero rows."],
        }

    if result.get("truncated") and chart_type in {"scatter", "histogram"}:
        caveats.append(f"Chart uses the first {result.get('row_count', len(rows)):,} rows returned by the query.")

    if chart_type == "kpi":
        text, highlights = _kpi_narrative(parsed, result, profile, fmt)
    elif chart_type == "line":
        text, highlights = _line_narrative(parsed, result, fmt)
    elif chart_type == "scatter":
        text, highlights = _scatter_narrative(parsed, result, caveats)
    elif chart_type == "histogram":
        text, highlights = _histogram_narrative(parsed, result, caveats)
    else:
        text, highlights = _bar_narrative(parsed, result, fmt)

    if result.get("truncated") and chart_type not in {"scatter", "histogram"}:
        caveats.append("The result set was truncated by the row limit.")
    facts.update({"highlights": highlights})
    return {"narrative": text.strip(), "highlights": highlights, "facts": facts, "caveats": caveats}


# --------------------------------------------------------------------------- #
# Chart-specific narration
# --------------------------------------------------------------------------- #
def _kpi_narrative(parsed: dict, result: dict, profile: dict, fmt: str) -> tuple[str, list[str]]:
    value = result["rows"][0][0]
    label = parsed.get("title", "Result")
    total_rows = profile.get("rows", 0)
    if parsed.get("intent") == "count":
        text = f"The dataset contains {_num(value, 'count')} records across {profile.get('cols', 0)} columns."
        return text, [f"{_num(value, 'count')} rows", f"{profile.get('cols', 0)} columns"]
    if fmt in {"percent_points", "percentage"}:
        text = f"{label} is {_num(value, fmt)}"
        if total_rows:
            text += f", measured across {total_rows:,} records."
        else:
            text += "."
        return text, [f"{_num(value, fmt)}"]
    text = f"{label} is {_num(value, fmt)}"
    if total_rows:
        text += f", calculated from {total_rows:,} records."
    else:
        text += "."
    return text, [f"{_num(value, fmt)}"]


def _bar_narrative(parsed: dict, result: dict, fmt: str) -> tuple[str, list[str]]:
    labels = [str(r[0]) if r[0] is not None else "—" for r in result["rows"]]
    values = [_to_float(r[1]) for r in result["rows"]]
    pairs = [(lab, val) for lab, val in zip(labels, values) if val is not None]
    if not pairs:
        return "No numeric values were returned.", []
    pairs.sort(key=lambda p: p[1], reverse=True)
    grain = parsed.get("grain")
    if grain:
        pairs = [(pretty_period(lab, grain), val) for lab, val in pairs]
    top_label, top_value = pairs[0]
    bottom_label, bottom_value = pairs[-1]
    total = sum(v for _, v in pairs if v > 0)
    is_rate = fmt in {"percent_points", "percentage"}
    is_average = bool(re.search(r"\bAVG\s*\(", parsed.get("sql", ""), re.I))
    highlights = [f"{top_label}: {_num(top_value, fmt)}"]
    if len(pairs) >= 2:
        second_label, second_value = pairs[1]
        highlights.append(f"{second_label}: {_num(second_value, fmt)}")
        if top_value:
            lead_gap = (top_value - second_value) / top_value
            highlights.append(f"Gap to second: {lead_gap:.0%}")

    if parsed.get("intent") == "time_rank" and grain:
        measure = (parsed.get("y_label") or "value").lower()
        text = f"{top_label} had the highest {measure} at {_num(top_value, fmt)}"
        if len(pairs) >= 2 and pairs[1][1] and top_value:
            gap = (top_value - pairs[1][1]) / top_value
            if gap >= 0.005:
                text += f", {gap:.0%} ahead of {pairs[1][0]} ({_num(pairs[1][1], fmt)})"
            else:
                text += f", essentially level with {pairs[1][0]} ({_num(pairs[1][1], fmt)})"
        text += "."
        if bottom_label != top_label:
            unit = grain if len(pairs) == 1 else f"{grain}s"
            text += (
                f" {bottom_label} was the lowest at {_num(bottom_value, fmt)} "
                f"across {len(pairs)} {unit}."
            )
        highlights = [f"{top_label}: {_num(top_value, fmt)}"]
        if len(pairs) >= 2:
            highlights.append(f"{pairs[1][0]}: {_num(pairs[1][1], fmt)}")
        if bottom_label != top_label:
            highlights.append(f"Lowest · {bottom_label}: {_num(bottom_value, fmt)}")
        return text, highlights[:3]

    if is_rate:
        text = (
            f"{top_label} has the highest {parsed.get('y_label', 'rate').lower()} at "
            f"{_num(top_value, fmt)}, versus {_num(bottom_value, fmt)} for {bottom_label}"
        )
        gap = top_value - bottom_value
        text += f" — a {gap:.1f} percentage-point spread across {len(pairs)} groups."
    elif is_average:
        text = (
            f"{top_label} has the highest average at {_num(top_value, fmt)}, compared with "
            f"{_num(bottom_value, fmt)} for {bottom_label}."
        )
        if bottom_value:
            text += f" That is a {top_value / bottom_value:.1f}× difference."
    else:
        share = top_value / total if total else None
        text = f"{top_label} leads with {_num(top_value, fmt)}"
        if share is not None:
            text += f", or {pct(share, 1)} of the {_num(total, fmt)} total"
        text += "."
        if len(pairs) >= 2 and pairs[1][1]:
            second_value = pairs[1][1]
            gap = (top_value - second_value) / top_value if top_value else 0.0
            if gap >= 0.005:
                text += (
                    f" {pairs[1][0]} is second at {_num(second_value, fmt)}, "
                    f"{gap:.0%} below the leader."
                )
            else:
                text += f" {pairs[1][0]} is essentially level at {_num(second_value, fmt)}."
    return text, highlights[:3]


def _line_narrative(parsed: dict, result: dict, fmt: str) -> tuple[str, list[str]]:
    labels = [str(r[0]) for r in result["rows"] if r[0] is not None]
    values = [_to_float(r[1]) for r in result["rows"]]
    pairs = [(lab, val) for lab, val in zip(labels, values) if val is not None]
    if len(pairs) < 2:
        return "Not enough periods to describe a trend.", []
    first_label, first_value = pairs[0]
    last_label, last_value = pairs[-1]
    peak_label, peak_value = max(pairs, key=lambda p: p[1])
    trough_label, trough_value = min(pairs, key=lambda p: p[1])
    change = (last_value - first_value) / abs(first_value) if first_value else None
    direction = "rose" if (change or 0) > 0.01 else "fell" if (change or 0) < -0.01 else "held steady"
    grain = parsed.get("grain", "period")
    y_label = parsed.get("y_label", "Value")
    text = (
        f"{y_label} {direction} from {_num(first_value, fmt)} in {_pretty_date(first_label, grain)} "
        f"to {_num(last_value, fmt)} in {_pretty_date(last_label, grain)}"
    )
    if change is not None:
        text += f" ({'+' if change >= 0 else ''}{change * 100:.1f}%)"
    text += f" across {len(pairs)} {grain if len(pairs) == 1 else grain + 's'}."
    trend = stats.ols_trend([v for _, v in pairs])
    if trend.get("r2") is not None:
        text += f" A linear trend explains {trend['r2'] * 100:.0f}% of the variation."
    text += f" Peak: {_num(peak_value, fmt)} in {_pretty_date(peak_label, grain)}."
    highlights = [
        f"{_pretty_date(first_label, grain)}: {_num(first_value, fmt)}",
        f"{_pretty_date(last_label, grain)}: {_num(last_value, fmt)}",
        f"Peak: {_num(peak_value, fmt)} ({_pretty_date(peak_label, grain)})",
    ]
    if change is not None:
        highlights.insert(2, f"Change: {'+' if change >= 0 else ''}{change * 100:.1f}%")
    return text, highlights[:4]


def _scatter_narrative(parsed: dict, result: dict, caveats: list[str]) -> tuple[str, list[str]]:
    rows = result["rows"]
    xs = [_to_float(r[0]) for r in rows]
    ys = [_to_float(r[1]) for r in rows]
    clean = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(clean) < 3:
        return "Not enough paired values to measure a relationship.", []
    xs, ys = zip(*clean)
    res = stats.pearson(xs, ys)
    r = res.get("r")
    if r is None:
        return "The relationship could not be computed.", []
    strength = "strong" if abs(r) >= 0.7 else "moderate" if abs(r) >= 0.4 else "weak"
    direction = "positive" if r > 0 else "negative"
    x_label = parsed.get("x_label", "X")
    y_label = parsed.get("y_label", "Y")
    text = (
        f"{x_label} and {y_label} show a {strength} {direction} relationship "
        f"(Pearson r = {r:.2f}, n = {len(clean):,})."
    )
    if abs(r) < 0.4:
        text += " The association is weak enough that other factors likely dominate."
    else:
        text += " As one rises, the other tends to rise too." if r > 0 else " As one rises, the other tends to fall."
    text += " This is an association, not proof of causation."
    if len(clean) < len(rows):
        caveats.append("Some rows had missing values and were excluded from the correlation.")
    return text, [f"r = {r:.2f}", f"n = {len(clean):,}", f"{strength.title()} {direction}"]


def _histogram_narrative(parsed: dict, result: dict, caveats: list[str]) -> tuple[str, list[str]]:
    values = [_to_float(r[0]) for r in result["rows"]]
    values = [v for v in values if v is not None]
    if len(values) < 3:
        return "Not enough values to describe the distribution.", []
    desc = stats.describe(values)
    fmt = parsed.get("value_format", "number")
    median, p25, p75 = desc["median"], desc["p25"], desc["p75"]
    skew = desc["skew"]
    shape = "right-skewed" if skew > 0.6 else "left-skewed" if skew < -0.6 else "roughly symmetric"
    text = (
        f"{pretty(parsed.get('x_label', 'Value'))} ranges from {_num(desc['min'], fmt)} to "
        f"{_num(desc['max'], fmt)}, with a median of {_num(median, fmt)} "
        f"(middle 50%: {_num(p25, fmt)} to {_num(p75, fmt)}). "
        f"The distribution is {shape} (skew {skew:.2f})."
    )
    if len(values) < 200:
        caveats.append("Distribution based on a small sample; interpret with care.")
    return text, [
        f"Median: {_num(median, fmt)}",
        f"Middle 50%: {_num(p25, fmt)} – {_num(p75, fmt)}",
        f"Skew: {skew:.2f} ({shape})",
    ]


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
def _num(value, fmt: str | None, digits: int = 1) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(v):
        return "—"
    if fmt == "currency":
        return "$" + compact(v)
    if fmt in {"percentage", "percent_points"}:
        return f"{v:.{digits}f}%"
    if fmt == "ratio":
        return f"{v:.2f}×"
    if fmt in {"count", "number"}:
        return compact(v)
    if abs(v) >= 1000:
        return compact(v)
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def _to_float(value) -> float | None:
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _pretty_date(label: str, grain: str) -> str:
    return pretty_period(label, grain)
