"""Small shared helpers: JSON serialization, identifier quoting, formatting."""
from __future__ import annotations

import html
import math
import re
import uuid
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


def jsonable(value: Any) -> Any:
    """Recursively convert numpy/pandas values into JSON-safe primitives."""
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        v = float(value)
        return None if not math.isfinite(v) else v
    if isinstance(value, np.datetime64):
        return None if np.isnat(value) else pd.Timestamp(value).isoformat()
    if isinstance(value, (pd.Timestamp, datetime, date)):
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        return value.isoformat()
    if isinstance(value, pd.Timedelta):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return [jsonable(v) for v in value.tolist()]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def pretty(name: str) -> str:
    """'churn_rate' -> 'Churn rate'; preserves acronyms like MRR and NPS."""
    text = re.sub(r"[_\-]+", " ", str(name)).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return text
    acronyms = {"id", "nps", "mrr", "arr", "roi", "ctr", "cvr", "api", "url", "ssn",
                "kpi", "gmv", "ltv", "cac", "sku", "uuid", "ip", "sql"}
    words = [w.upper() if w.lower() in acronyms else w for w in text.split(" ")]
    words[0] = words[0][:1].upper() + words[0][1:]
    return " ".join(words)


def quote_ident(name: str) -> str:
    """Quote a DuckDB identifier, escaping embedded double quotes."""
    return '"' + str(name).replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def table_name(dataset_id: str) -> str:
    return "ds_" + re.sub(r"[^a-zA-Z0-9]", "", dataset_id)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def compact(x: float | int | None, digits: int = 1) -> str:
    """Human-friendly number: 1.24M, 18.3K, 0.82."""
    if x is None:
        return "—"
    try:
        x = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not math.isfinite(x):
        return "—"
    sign = "-" if x < 0 else ""
    ax = abs(x)
    if ax >= 1e12:
        return f"{sign}{ax / 1e12:.{digits}f}T"
    if ax >= 1e9:
        return f"{sign}{ax / 1e9:.{digits}f}B"
    if ax >= 1e6:
        return f"{sign}{ax / 1e6:.{digits}f}M"
    if ax >= 1e3:
        return f"{sign}{ax / 1e3:.{digits}f}K"
    if ax == int(ax):
        return f"{sign}{int(ax):,}"
    return f"{sign}{ax:,.{max(digits, 2)}f}".rstrip("0").rstrip(".")


def pct(x: float | None, digits: int = 1) -> str:
    if x is None or not isinstance(x, (int, float)) or not math.isfinite(x):
        return "—"
    return f"{x * 100:.{digits}f}%"


def escape(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def slugify(text: str, fallback: str = "dataset") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return slug[:60] or fallback


def truncate(text: str, limit: int = 120) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def as_float(value: Any) -> float | None:
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def pretty_period(label: Any, grain: str | None = "month") -> str:
    """Format an ISO period label for display: ``2026-09-01`` -> ``Sep 2026``."""
    text = str(label).replace("T00:00:00", "")
    day = grain in {"day", "date"} or (grain is None and len(text) > 7)
    for fmt_in in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m", "%Y"):
        try:
            parsed = datetime.strptime(text[:19], fmt_in)
        except ValueError:
            continue
        if grain == "year":
            return parsed.strftime("%Y")
        if grain == "quarter":
            return f"Q{(parsed.month - 1) // 3 + 1} {parsed.year}"
        return parsed.strftime("%b %d, %Y" if day else "%b %Y")
    return str(label)


def human_bytes(size: float | int | None) -> str:
    if not size:
        return "0 B"
    n = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
