"""Semantic typing: what a column *means*, not just what dtype it has.

This is the difference between a spreadsheet and an analyst. ``revenue`` is a
currency measure, ``churn_rate`` is a percentage measure, ``account_id`` is an
identifier, ``contact_email`` is PII, and ``region`` is a categorical dimension.
"""
from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from .util import pretty

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]{2,}$")
URL_RE = re.compile(r"^https?://[^\s]+$", re.I)
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
IPV4_RE = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$")
PHONE_RE = re.compile(r"^\+?[\d\s().-]{7,20}$")
SSN_RE = re.compile(r"^\d{3}-\d{2}-\d{4}$")
CURRENCY_RE = re.compile(r"^[\s]*[$€£¥₹]")
PERCENT_RE = re.compile(r"%\s*$")

CURRENCY_HINTS = {
    "revenue", "mrr", "arr", "sales", "spend", "cost", "price", "amount", "income",
    "salary", "budget", "profit", "margin", "payment", "value", "gmv", "ltv", "cac",
    "wages", "fee", "fees", "balance",
}
PERCENT_HINTS = {
    "rate", "pct", "percent", "percentage", "ratio", "share", "conversion", "churn",
    "growth", "margin", "probability", "retention", "uplift", "ctr", "cvr", "roi",
}
COUNT_HINTS = {"count", "qty", "quantity", "units", "seats", "tickets", "clicks", "impressions", "leads", "conversions", "customers", "users", "visits", "trials"}
ID_HINTS = {"id", "key", "code", "sku", "uuid", "guid", "ref", "number", "no"}
DATE_HINTS = {"date", "day", "week", "month", "quarter", "year", "timestamp", "time", "period", "created", "updated", "signup"}
PHONE_HINTS = {"phone", "mobile", "tel", "telephone", "cell", "fax"}

TRUE_VALUES = {"true", "t", "yes", "y", "1"}
FALSE_VALUES = {"false", "f", "no", "n", "0"}
COUNTRIES = {
    "US", "GB", "DE", "FR", "ES", "IT", "NL", "SE", "NO", "DK", "FI", "IE", "PT", "PL",
    "CA", "MX", "BR", "AR", "CL", "CO", "PE", "AU", "NZ", "JP", "CN", "IN", "SG", "KR",
    "ID", "MY", "TH", "VN", "PH", "AE", "SA", "IL", "TR", "ZA", "NG", "KE", "EG", "RU",
    "UA", "CH", "AT", "BE", "CZ", "GR", "HU", "RO", "HK", "TW",
}


def _tokens(name: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", str(name).lower()) if t}


def _name_has(name: str, hints: set[str] | list[str]) -> bool:
    hints = set(hints)
    low = str(name).lower()
    toks = _tokens(name)
    if toks & hints:
        return True
    return any(low.endswith(h) for h in hints if not h.isdigit())


def parse_number(value: Any) -> float | None:
    """Parse a business-formatted number: $1,234.50, (12.4), 7.2%, 1 234."""
    if value is None:
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        v = float(value)
        return v if np.isfinite(v) else None
    s = str(value).strip()
    if not s or s.lower() in {"na", "n/a", "null", "none", "-", "--", "nan", "?"}:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").strip()
    s = re.sub(r"(?i)\b(usd|eur|gbp|jpy|chf|cad|aud|inr)\b", "", s)
    s = s.replace(",", "").replace("$", "").replace("€", "").replace("£", "").replace("¥", "").replace("₹", "")
    s = s.replace("\u00a0", "").replace(" ", "").rstrip("%")
    try:
        v = float(s)
    except ValueError:
        return None
    if not np.isfinite(v):
        return None
    return -v if neg else v


def _numeric_ratio(values: list[str]) -> float:
    if not values:
        return 0.0
    parsed = sum(1 for v in values if parse_number(v) is not None)
    return parsed / len(values)


def luhn_ok(value: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", value)]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _match_ratio(values: list[str], regex: re.Pattern) -> float:
    if not values:
        return 0.0
    return sum(1 for v in values if regex.match(v.strip())) / len(values)


def detect(name: str, series: pd.Series, dtype: Any) -> dict:
    """Return semantic metadata for one column."""
    non_null = series.dropna()
    n = int(non_null.size)
    distinct = int(non_null.nunique()) if n else 0
    samples = [str(v).strip() for v in non_null.head(400).tolist()]
    low_name = str(name).lower()
    result = {
        "semantic": "text",
        "role": "text",
        "confidence": 0.5,
        "format": None,
        "pii": False,
    }

    if n == 0:
        result.update({"semantic": "empty", "role": "empty", "confidence": 1.0})
        return result

    if pd.api.types.is_bool_dtype(series):
        return {**result, "semantic": "boolean", "role": "dimension", "confidence": 0.99}

    if pd.api.types.is_datetime64_any_dtype(series):
        granularity = _date_granularity(non_null)
        return {**result, "semantic": "datetime" if granularity == "time" else "date",
                "role": "time", "confidence": 0.99, "format": granularity}

    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        if _name_has(name, ID_HINTS) and distinct == n and n > 20:
            return {**result, "semantic": "id", "role": "identifier", "confidence": 0.8}
        if _name_has(name, CURRENCY_HINTS):
            return {**result, "semantic": "currency", "role": "measure", "confidence": 0.9,
                    "format": "currency"}
        if _name_has(name, PERCENT_HINTS):
            return {**result, "semantic": "percentage", "role": "measure", "confidence": 0.9,
                    "format": "percent"}
        if _name_has(name, COUNT_HINTS):
            return {**result, "semantic": "count", "role": "measure", "confidence": 0.85}
        if distinct <= 2 and set(np.unique(non_null).astype(str)) <= {"0", "1", "0.0", "1.0"}:
            return {**result, "semantic": "boolean", "role": "dimension", "confidence": 0.7}
        if distinct <= 12 and n > 20:
            return {**result, "semantic": "ordinal", "role": "dimension", "confidence": 0.65}
        return {**result, "semantic": "number", "role": "measure", "confidence": 0.9}

    # ---- string-like columns -------------------------------------------------
    if samples:
        if _match_ratio(samples, EMAIL_RE) > 0.9:
            return {**result, "semantic": "email", "role": "identifier", "confidence": 0.99,
                    "pii": True}
        if _match_ratio(samples, UUID_RE) > 0.9:
            return {**result, "semantic": "uuid", "role": "identifier", "confidence": 0.99}
        if _match_ratio(samples, URL_RE) > 0.9:
            return {**result, "semantic": "url", "role": "text", "confidence": 0.95}
        if _match_ratio(samples, IPV4_RE) > 0.95:
            return {**result, "semantic": "ip_address", "role": "identifier", "confidence": 0.95}
        if _match_ratio(samples, SSN_RE) > 0.9:
            return {**result, "semantic": "ssn", "role": "identifier", "confidence": 0.97, "pii": True}
        # Date and card checks precede phone: ISO dates and decimal numbers both
        # fit the loose phone pattern and must not be mislabelled as PII.
        if _name_has(name, DATE_HINTS) and _datetime_ratio(samples) > 0.8:
            return {**result, "semantic": "date", "role": "time", "confidence": 0.8,
                    "format": "day"}
        card_samples = [s for s in samples if re.fullmatch(r"[\d -]{13,23}", s)]
        if len(card_samples) >= 5 and all(luhn_ok(s) for s in card_samples[:8]):
            return {**result, "semantic": "credit_card", "role": "identifier", "confidence": 0.95, "pii": True}
        if _name_has(name, PHONE_HINTS) and _match_ratio(samples, PHONE_RE) > 0.6:
            return {**result, "semantic": "phone", "role": "identifier", "confidence": 0.9, "pii": True}

        uniq_ratio = distinct / n if n else 0
        if uniq_ratio > 0.98 and _name_has(name, ID_HINTS):
            return {**result, "semantic": "id", "role": "identifier", "confidence": 0.95}

        lowered = {s.lower() for s in samples[:200]}
        if len(lowered) <= 2 and lowered <= (TRUE_VALUES | FALSE_VALUES):
            return {**result, "semantic": "boolean", "role": "dimension", "confidence": 0.9}

        if _name_has(name, ["country", "country_code", "market"]) or (
            all(len(s) == 2 and s.upper() in COUNTRIES for s in samples[:100]) and len(set(samples[:100])) <= 40
        ):
            return {**result, "semantic": "country", "role": "dimension", "confidence": 0.85}

        money = sum(1 for s in samples if CURRENCY_RE.match(s)) / len(samples)
        pct_sign = sum(1 for s in samples if PERCENT_RE.search(s)) / len(samples)
        numeric = _numeric_ratio(samples)
        if pct_sign > 0.6:
            return {**result, "semantic": "percentage", "role": "measure", "confidence": 0.85,
                    "format": "percent"}
        if money > 0.5:
            return {**result, "semantic": "currency", "role": "measure", "confidence": 0.9,
                    "format": "currency"}
        if numeric > 0.95:
            if _name_has(name, CURRENCY_HINTS):
                return {**result, "semantic": "currency", "role": "measure", "confidence": 0.85,
                        "format": "currency"}
            return {**result, "semantic": "number", "role": "measure", "confidence": 0.8}
        if uniq_ratio > 0.98 and distinct > 50 and (sum(len(s) for s in samples) / len(samples)) < 40:
            return {**result, "semantic": "identifier", "role": "identifier", "confidence": 0.75}
        if _match_ratio(samples, PHONE_RE) > 0.9 and sum(c.isdigit() for c in "".join(samples)) / max(1, len(samples)) > 6:
            return {**result, "semantic": "phone", "role": "identifier", "confidence": 0.9, "pii": True}

    # categorical vs free text
    if distinct <= 2:
        return {**result, "semantic": "boolean", "role": "dimension", "confidence": 0.7}
    if distinct <= 50 and (distinct / n if n else 0) < 0.5:
        return {**result, "semantic": "category", "role": "dimension", "confidence": 0.85}
    if distinct / n < 0.2 if n else False:
        return {**result, "semantic": "category", "role": "dimension", "confidence": 0.7}
    return {**result, "semantic": "text", "role": "text", "confidence": 0.7,
            "pii": bool(re.search(r"(email|phone|name|address)", low_name))}


def _datetime_ratio(values: list[str]) -> float:
    sample = values[:200]
    ok = 0
    for v in sample:
        try:
            parsed = pd.to_datetime(v, errors="coerce", format="mixed")
            if not pd.isna(parsed):
                ok += 1
        except (ValueError, TypeError):
            pass
    return ok / len(sample) if sample else 0.0


def _date_granularity(series: pd.Series) -> str:
    try:
        times = series.dropna().head(200)
        if len(times) < 2:
            return "day"
        if all((t.hour, t.minute, t.second) == (0, 0, 0) for t in times if hasattr(t, "hour")):
            return "day"
        return "time"
    except (TypeError, ValueError):
        return "day"


def is_measure(col: dict) -> bool:
    return col.get("role") == "measure" and col.get("semantic") in {"number", "currency", "count", "percentage", "ordinal"}


def is_dimension(col: dict) -> bool:
    return col.get("role") in {"dimension", "time"} and col.get("semantic") not in {"id", "email", "empty"}
