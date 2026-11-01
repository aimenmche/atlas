"""Server-side SVG charts.

The live interface draws with the browser's own canvas-free SVG layer, but the
exported report is a single self-contained HTML file. Rather than ship a chart
library inside that file, Atlas renders its insight charts to SVG here.
"""
from __future__ import annotations

import html
import math
from typing import Any, Sequence

from .util import compact

INK = "#0b0f14"
PANEL = "#111820"
GRID = "#1f2a37"
TEXT = "#e7eef6"
MUTED = "#8b98a9"
ACCENT = "#5eead4"
ACCENT_2 = "#7dd3fc"
AMBER = "#fbbf24"
ROSE = "#fb7185"
FONT = "Inter, 'Segoe UI', system-ui, -apple-system, sans-serif"


# --------------------------------------------------------------------------- #
# Public
# --------------------------------------------------------------------------- #
def render_chart(chart: dict, width: int = 760, height: int = 300) -> str:
    kind = (chart or {}).get("type")
    if kind == "bar":
        return bar_svg(
            chart.get("labels") or [],
            chart.get("values") or [],
            fmt=chart.get("format") or chart.get("value_format") or "number",
            width=width,
            height=height,
            x_label=chart.get("x_label"),
            horizontal=bool(chart.get("horizontal", True)),
        )
    if kind == "line":
        return line_svg(
            chart.get("labels") or [],
            chart.get("values") or [],
            fmt=chart.get("format") or chart.get("value_format") or "number",
            width=width,
            height=height,
            anomalies=chart.get("anomalies") or [],
        )
    if kind == "scatter":
        return scatter_svg(
            chart.get("points") or [],
            x_label=chart.get("x_label") or "X",
            y_label=chart.get("y_label") or "Y",
            x_format=chart.get("x_format") or "number",
            y_format=chart.get("y_format") or "number",
            width=width,
            height=height,
        )
    if kind == "histogram":
        return histogram_svg(
            chart.get("counts") or [],
            chart.get("edges") or [],
            fmt=chart.get("format") or "number",
            width=width,
            height=height,
        )
    if kind == "kpi":
        return kpi_svg(chart.get("value"), chart.get("label") or "", fmt=chart.get("format") or "number")
    return _empty_svg("No chart available", width, height)


def fmt_value(value: Any, fmt: str | None = None, compact_value: bool = True) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return html.escape(str(value))
    if not math.isfinite(number):
        return "—"
    if fmt == "currency":
        sign = "-" if number < 0 else ""
        return f"{sign}${compact(abs(number)) if compact_value else f'{abs(number):,.0f}'}"
    if fmt in {"percentage", "percent_points"}:
        return f"{number:.1f}%"
    if fmt == "ratio":
        return f"{number:.2f}×"
    if abs(number) >= 1000 and compact_value:
        return compact(number)
    if number == int(number):
        return f"{int(number):,}"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- #
# Bar
# --------------------------------------------------------------------------- #
def bar_svg(
    labels: Sequence[str],
    values: Sequence[float | None],
    fmt: str = "number",
    width: int = 760,
    height: int = 300,
    x_label: str | None = None,
    horizontal: bool = True,
    color: str = ACCENT,
) -> str:
    pairs = [(str(lab), _num(val)) for lab, val in zip(labels, values)]
    pairs = [p for p in pairs if p[1] is not None]
    if not pairs:
        return _empty_svg("No values to chart", width, height)
    if horizontal:
        pairs.sort(key=lambda p: p[1], reverse=True)
    if not horizontal:
        return _column_svg(pairs, fmt, width, height, color)
    pairs = pairs[:18]
    left, right, top, bottom = 168, 78, 16, 28
    plot_w = max(40, width - left - right)
    plot_h = max(40, height - top - bottom)
    row = plot_h / len(pairs)
    thickness = min(26.0, row * 0.62)
    low = min(0.0, min(v for _, v in pairs))
    high = max(0.0, max(v for _, v in pairs))
    span = (high - low) or 1.0
    zero_x = left + (0 - low) / span * plot_w
    parts = [_svg_open(width, height)]
    parts.append(_grid_x(left, top, plot_w, plot_h, low, high, fmt))
    for i, (label, value) in enumerate(pairs):
        y = top + row * i + (row - thickness) / 2
        end_x = left + (value - low) / span * plot_w
        x = min(zero_x, end_x)
        w = max(1.5, abs(end_x - zero_x))
        fill = color if value >= 0 else ROSE
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{thickness:.1f}" rx="4" '
            f'fill="{fill}" fill-opacity="0.9"><title>{_esc(label)}: {fmt_value(value, fmt)}</title></rect>'
        )
        parts.append(
            f'<text x="{left - 12}" y="{y + thickness / 2 + 4:.1f}" text-anchor="end" '
            f'font-size="12.5" fill="{TEXT}">{_ellipsis(label, 24)}</text>'
        )
        anchor = "start" if value >= 0 else "end"
        tx = end_x + (9 if value >= 0 else -9)
        parts.append(
            f'<text x="{tx:.1f}" y="{y + thickness / 2 + 4:.1f}" text-anchor="{anchor}" '
            f'font-size="12" font-weight="600" fill="{TEXT}" fill-opacity="0.92">{fmt_value(value, fmt)}</text>'
        )
    if x_label:
        parts.append(_axis_title(x_label, left + plot_w / 2, height - 4))
    parts.append("</svg>")
    return "".join(parts)


def _column_svg(pairs: list[tuple[str, float]], fmt: str, width: int, height: int, color: str) -> str:
    pairs = pairs[:12]
    left, right, top, bottom = 56, 20, 24, 52
    plot_w = max(40, width - left - right)
    plot_h = max(40, height - top - bottom)
    high = max(0.0, max(v for _, v in pairs))
    low = min(0.0, min(v for _, v in pairs))
    span = (high - low) or 1.0
    slot = plot_w / len(pairs)
    bar_w = min(54, slot * 0.58)
    parts = [_svg_open(width, height), _grid_x(left, top, plot_w, plot_h, low, high, fmt)]
    zero_y = top + (high - 0) / span * plot_h
    for i, (label, value) in enumerate(pairs):
        cx = left + slot * (i + 0.5)
        end_y = top + (high - value) / span * plot_h
        y = min(zero_y, end_y)
        h = max(1.5, abs(end_y - zero_y))
        parts.append(
            f'<rect x="{cx - bar_w / 2:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" rx="3" '
            f'fill="{color}" fill-opacity="0.9"><title>{_esc(label)}: {fmt_value(value, fmt)}</title></rect>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{min(top + plot_h + 16, height - 8):.1f}" text-anchor="middle" '
            f'font-size="11" fill="{MUTED}">{_ellipsis(label, 12)}</text>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{y - 6:.1f}" text-anchor="middle" font-size="10.5" '
            f'fill="{TEXT}" fill-opacity="0.85">{fmt_value(value, fmt)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Line
# --------------------------------------------------------------------------- #
def line_svg(
    labels: Sequence[str],
    values: Sequence[float | None],
    fmt: str = "number",
    width: int = 760,
    height: int = 300,
    color: str = ACCENT,
    anomalies: Sequence[dict] | None = None,
) -> str:
    pairs = [(str(lab), _num(val)) for lab, val in zip(labels, values)]
    pairs = [p for p in pairs if p[1] is not None]
    if len(pairs) < 2:
        return _empty_svg("Not enough points to chart a trend", width, height)
    left, right, top, bottom = 62, 34, 24, 40
    plot_w = max(40, width - left - right)
    plot_h = max(40, height - top - bottom)
    ys = [v for _, v in pairs]
    low, high = min(ys), max(ys)
    if low == high:
        low, high = low - 1, high + 1
    pad = (high - low) * 0.12
    low -= pad
    high += pad
    span = high - low

    def point(i: int, v: float) -> tuple[float, float]:
        x = left + (plot_w * i / (len(pairs) - 1))
        y = top + (high - v) / span * plot_h
        return x, y

    pts = [point(i, v) for i, (_, v) in enumerate(pairs)]
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = path + f" L{pts[-1][0]:.1f},{top + plot_h:.1f} L{pts[0][0]:.1f},{top + plot_h:.1f} Z"
    gid = f"g{abs(hash((tuple(labels), tuple(ys)))) % 10_000_000}"

    parts = [_svg_open(width, height)]
    parts.append(
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{color}" stop-opacity="0.28"/>'
        f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
    )
    parts.append(_grid_y(left, top, plot_w, plot_h, low, high, fmt))
    parts.append(f'<path d="{area}" fill="url(#{gid})"/>')
    parts.append(
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.4" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
    )
    if len(pts) <= 31:
        for (label, value), (x, y) in zip(pairs, pts):
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{PANEL}" stroke="{color}" stroke-width="1.8">'
                f'<title>{_esc(label)}: {fmt_value(value, fmt)}</title></circle>'
            )
    for flag in anomalies or []:
        index = flag.get("index")
        if not isinstance(index, int) or not 0 <= index < len(pts):
            continue
        x, y = pts[index]
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.6" fill="none" stroke="{ROSE}" stroke-width="1.8" '
            f'stroke-opacity="0.9"><title>{_esc(str(flag.get("label", "")))}: {fmt_value(flag.get("value"), fmt)} '
            f'(z {flag.get("z", "—")})</title></circle>'
        )
    # x labels: first, last, and up to four in between.
    indices = _tick_indices(len(pairs), 6)
    for i in indices:
        x, _ = pts[i]
        anchor = "start" if i == 0 else "end" if i == len(pairs) - 1 else "middle"
        parts.append(
            f'<text x="{x:.1f}" y="{top + plot_h + 20:.1f}" text-anchor="{anchor}" font-size="11" '
            f'fill="{MUTED}">{_esc(_short_label(pairs[i][0]))}</text>'
        )
    # last point annotation
    lx, ly = pts[-1]
    last_value = pairs[-1][1]
    parts.append(
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="5" fill="{color}" fill-opacity="0.22"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="{color}"/>'
    )
    label = fmt_value(last_value, fmt)
    pill_w = max(44, 7.2 * len(label) + 16)
    px = min(width - pill_w - 4, lx - pill_w / 2)
    py = max(2, ly - 30)
    parts.append(
        f'<rect x="{px:.1f}" y="{py:.1f}" width="{pill_w:.1f}" height="20" rx="10" '
        f'fill="{color}" fill-opacity="0.14" stroke="{color}" stroke-opacity="0.35"/>'
        f'<text x="{px + pill_w / 2:.1f}" y="{py + 14:.1f}" text-anchor="middle" font-size="11" '
        f'font-weight="600" fill="{color}">{label}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Scatter
# --------------------------------------------------------------------------- #
def scatter_svg(
    points: Sequence[Sequence[float]],
    x_label: str = "X",
    y_label: str = "Y",
    x_format: str = "number",
    y_format: str = "number",
    width: int = 760,
    height: int = 300,
    color: str = ACCENT_2,
) -> str:
    clean = [(float(p[0]), float(p[1])) for p in points if len(p) >= 2 and _num(p[0]) is not None and _num(p[1]) is not None]
    if len(clean) < 2:
        return _empty_svg("Not enough paired values to chart", width, height)
    if len(clean) > 1600:
        step = len(clean) / 1600
        clean = [clean[int(i * step)] for i in range(1600)]
    left, right, top, bottom = 66, 22, 22, 46
    plot_w = max(40, width - left - right)
    plot_h = max(40, height - top - bottom)
    xs = [p[0] for p in clean]
    ys = [p[1] for p in clean]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x0 == x1:
        x0, x1 = x0 - 1, x1 + 1
    if y0 == y1:
        y0, y1 = y0 - 1, y1 + 1
    xp = (x1 - x0) * 0.05
    yp = (y1 - y0) * 0.08
    x0, x1 = x0 - xp, x1 + xp
    y0, y1 = y0 - yp, y1 + yp

    def sx(v: float) -> float:
        return left + (v - x0) / (x1 - x0) * plot_w

    def sy(v: float) -> float:
        return top + (y1 - v) / (y1 - y0) * plot_h

    parts = [_svg_open(width, height), _grid_xy(left, top, plot_w, plot_h, x0, x1, y0, y1, x_format, y_format)]
    for x, y in clean:
        parts.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="2.9" fill="{color}" fill-opacity="0.5"/>')
    # least-squares reference line
    if len(clean) >= 3:
        n = len(clean)
        mx, my = sum(xs) / n, sum(ys) / n
        denom = sum((x - mx) ** 2 for x in xs)
        if denom:
            slope = sum((x - mx) * (y - my) for x, y in clean) / denom
            intercept = my - slope * mx
            y_at_x0 = intercept + slope * x0
            y_at_x1 = intercept + slope * x1
            parts.append(
                f'<line x1="{sx(x0):.1f}" y1="{sy(y_at_x0):.1f}" x2="{sx(x1):.1f}" y2="{sy(y_at_x1):.1f}" '
                f'stroke="{AMBER}" stroke-width="1.6" stroke-dasharray="6 5" stroke-opacity="0.8"/>'
            )
    parts.append(
        f'<text x="{left + plot_w / 2:.1f}" y="{height - 8}" text-anchor="middle" font-size="11.5" '
        f'fill="{MUTED}">{_esc(x_label)}</text>'
    )
    parts.append(
        f'<text transform="translate(14,{top + plot_h / 2:.1f}) rotate(-90)" text-anchor="middle" '
        f'font-size="11.5" fill="{MUTED}">{_esc(y_label)}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Histogram
# --------------------------------------------------------------------------- #
def histogram_svg(
    counts: Sequence[int],
    edges: Sequence[float],
    fmt: str = "number",
    width: int = 760,
    height: int = 300,
    color: str = AMBER,
) -> str:
    counts = [int(c) for c in counts]
    if len(counts) < 2 or len(edges) < len(counts) + 1:
        return _empty_svg("Not enough values to chart a distribution", width, height)
    left, right, top, bottom = 56, 20, 22, 42
    plot_w = max(40, width - left - right)
    plot_h = max(40, height - top - bottom)
    high = max(counts) or 1
    slot = plot_w / len(counts)
    bar_w = max(3, slot - 2.5)
    parts = [_svg_open(width, height)]
    for tick in range(4):
        value = high * tick / 3
        y = top + plot_h - (value / high) * plot_h
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" font-size="10.5" fill="{MUTED}">{compact(value)}</text>'
        )
    total = sum(counts) or 1
    for i, count in enumerate(counts):
        h = (count / high) * plot_h
        x = left + i * slot + (slot - bar_w) / 2
        y = top + plot_h - h
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(1, h):.1f}" rx="2" '
            f'fill="{color}" fill-opacity="0.8"><title>{count:,} rows ({count / total * 100:.1f}%)</title></rect>'
        )
    # median marker
    if len(edges) >= 2:
        mid = (edges[0] + edges[-1]) / 2
        parts.append(
            f'<text x="{left + plot_w / 2:.1f}" y="{top + plot_h + 18:.1f}" text-anchor="middle" '
            f'font-size="10.5" fill="{MUTED}">midpoint {fmt_value(mid, fmt)} · n = {total:,}</text>'
        )
        parts.append(
            f'<text x="{left}" y="{top + plot_h + 18:.1f}" text-anchor="start" font-size="10.5" fill="{MUTED}">'
            f'{fmt_value(edges[0], fmt)}</text>'
        )
        parts.append(
            f'<text x="{left + plot_w}" y="{top + plot_h + 18:.1f}" text-anchor="end" font-size="10.5" fill="{MUTED}">'
            f'{fmt_value(edges[-1], fmt)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# KPI
# --------------------------------------------------------------------------- #
def kpi_svg(value: Any, label: str, fmt: str = "number") -> str:
    return (
        f'<div class="kpi"><div class="kpi-value">{fmt_value(value, fmt)}</div>'
        f'<div class="kpi-label">{_esc(label)}</div></div>'
    )


# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #
def _svg_open(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" style="display:block;height:auto" role="img" font-family="{FONT}">'
    )


def _grid_x(left: int, top: int, plot_w: float, plot_h: float, low: float, high: float, fmt: str) -> str:
    parts = []
    for tick in range(5):
        value = low + (high - low) * tick / 4
        x = left + plot_w * tick / 4
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{top + plot_h + 18:.1f}" text-anchor="middle" font-size="10" fill="{MUTED}">'
            f'{fmt_value(value, fmt)}</text>'
        )
    return "".join(parts)


def _grid_y(left: int, top: int, plot_w: float, plot_h: float, low: float, high: float, fmt: str) -> str:
    parts = []
    for tick in range(5):
        value = low + (high - low) * tick / 4
        y = top + plot_h - (value - low) / (high - low) * plot_h
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(
            f'<text x="{left - 9}" y="{y + 4:.1f}" text-anchor="end" font-size="10" fill="{MUTED}">'
            f'{fmt_value(value, fmt)}</text>'
        )
    return "".join(parts)


def _grid_xy(left, top, plot_w, plot_h, x0, x1, y0, y1, xfmt, yfmt) -> str:
    parts = []
    for tick in range(4):
        y = top + plot_h * tick / 3
        value = y1 - (y1 - y0) * tick / 3
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(
            f'<text x="{left - 9}" y="{y + 4:.1f}" text-anchor="end" font-size="10" fill="{MUTED}">'
            f'{fmt_value(value, yfmt)}</text>'
        )
    for tick in range(4):
        x = left + plot_w * tick / 3
        value = x0 + (x1 - x0) * tick / 3
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" stroke="{GRID}" stroke-width="1" stroke-opacity="0.7"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{top + plot_h + 18:.1f}" text-anchor="middle" font-size="10" fill="{MUTED}">'
            f'{fmt_value(value, xfmt)}</text>'
        )
    return "".join(parts)


def _axis_title(text: str, x: float, y: float) -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" font-size="11" fill="{MUTED}">{_esc(text)}</text>'


def _empty_svg(message: str, width: int, height: int) -> str:
    return (
        _svg_open(width, height)
        + f'<rect x="0" y="0" width="{width}" height="{height}" fill="none"/>'
        + f'<text x="{width / 2}" y="{height / 2}" text-anchor="middle" font-size="13" fill="{MUTED}">{_esc(message)}</text>'
        + "</svg>"
    )


def _tick_indices(n: int, count: int) -> list[int]:
    if n <= count:
        return list(range(n))
    step = (n - 1) / (count - 1)
    return sorted({int(round(step * i)) for i in range(count)})


def _short_label(label: str) -> str:
    text = str(label)
    for suffix in ("T00:00:00", " 00:00:00"):
        text = text.replace(suffix, "")
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        try:
            return f"{months[int(text[5:7]) - 1]} {text[8:10]} '{text[2:4]}"
        except (ValueError, IndexError):
            return text
    if len(text) == 7 and text[4] == "-":
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        try:
            return f"{months[int(text[5:7]) - 1]} {text[:4]}"
        except (ValueError, IndexError):
            return text
    return text


def _ellipsis(text: str, limit: int) -> str:
    text = str(text)
    return html.escape(text if len(text) <= limit else text[: limit - 1] + "…")


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
