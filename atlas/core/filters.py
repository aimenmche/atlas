"""Segment filters shared by Ask and the Explore console.

A filter is a simple ``column = value`` pair. Atlas applies it by wrapping the
dataset table in a filtered subquery, which keeps every downstream aggregate,
window function and ORDER BY valid without string-patching arbitrary SQL.
"""
from __future__ import annotations

from typing import Any

from .util import quote_ident, quote_literal

MAX_FILTERS = 8
MAX_VALUE_LENGTH = 200


def clean_filters(filters: list[dict] | None, columns: set[str] | None = None) -> list[dict]:
    """Normalise and bound filter values, optionally rejecting unknown columns."""
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in (filters or [])[:MAX_FILTERS]:
        if not isinstance(item, dict):
            continue
        column = " ".join(str(item.get("column") or "").split())[:80]
        value = " ".join(str(item.get("value") or "").split())[:MAX_VALUE_LENGTH]
        if not column or not value:
            continue
        if columns is not None and column not in columns:
            continue
        key = (column, value.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"column": column, "value": value})
    return out


def filter_clause(filters: list[dict]) -> str:
    return " AND ".join(
        f"CAST({quote_ident(item['column'])} AS VARCHAR) = {quote_literal(item['value'])}"
        for item in filters
    )


def apply_filters(sql: str, table: str, filters: list[dict] | None) -> str:
    """Wrap the dataset table in a filtered subquery.

    ``{table}`` placeholders are supported as well as quoted table names, so
    this works for Explore templates and generated analyst SQL alike.
    """
    cleaned = clean_filters(filters)
    if not cleaned:
        return sql
    quoted = quote_ident(table)
    filtered = f"(SELECT * FROM {quoted} WHERE {filter_clause(cleaned)}) AS {quoted}"
    if "{table}" in sql:
        return sql.replace("{table}", filtered)
    if quoted in sql:
        return sql.replace(quoted, filtered)
    return sql


def describe_filters(filters: list[dict] | None) -> str:
    cleaned = clean_filters(filters)
    if not cleaned:
        return ""
    return ", ".join(f"{item['column']} = {item['value']}" for item in cleaned)


def serialize_filters(filters: list[dict] | None) -> list[dict[str, Any]]:
    return [{"column": item["column"], "value": item["value"]} for item in clean_filters(filters)]
