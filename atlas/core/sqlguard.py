"""SQL safety: Atlas only ever runs read-only, single-statement queries.

Layered defence:
1. DuckDB itself is opened with ``enable_external_access=false`` (no file/http).
2. This module rejects anything that is not a single SELECT/WITH.
3. Queries are wrapped with a row limit and executed under a watchdog timeout.
"""
from __future__ import annotations

import re

MAX_SQL_LENGTH = 50_000
FORBIDDEN_KEYWORDS = {
    "attach", "detach", "install", "load", "copy", "export", "import", "pragma",
    "set", "reset", "call", "create", "drop", "alter", "insert", "update", "delete",
    "truncate", "vacuum", "checkpoint", "use", "begin", "commit", "rollback",
    "grant", "revoke", "comment", "analyze", "merge", "replace", "upsert",
}
FORBIDDEN_FUNCTIONS = {
    "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto",
    "read_text", "read_blob", "parquet_scan", "csv_scan", "json_scan", "glob",
    "httpfs", "sqlite_scan", "postgres_scan", "mysql_scan", "duckdb_extensions",
    "getvariable", "current_setting", "shell", "system",
}
SELECT_START = re.compile(r"^\s*(select|with)\b", re.I)


class SqlRejected(ValueError):
    """Raised when a query violates the read-only policy."""


def validate_sql(sql: str) -> str:
    if not sql or not sql.strip():
        raise SqlRejected("The query is empty.")
    if len(sql) > MAX_SQL_LENGTH:
        raise SqlRejected("The query is too long.")
    cleaned = _strip_comments(sql).strip()
    masked = _mask_literals(cleaned)
    cleaned = cleaned.rstrip(";").strip()
    masked = masked.rstrip(";").strip()
    if ";" in masked:
        raise SqlRejected("Only one statement per query is allowed.")
    if not SELECT_START.match(cleaned):
        raise SqlRejected("Only SELECT queries are allowed.")
    lowered = masked.lower()
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", lowered):
            raise SqlRejected(f"The keyword '{keyword}' is not allowed in analyst queries.")
    for fn in FORBIDDEN_FUNCTIONS:
        if re.search(rf"\b{fn}\s*\(", lowered):
            raise SqlRejected(f"The function '{fn}' is disabled.")
    return cleaned


def _mask_literals(sql: str) -> str:
    """Blank string literals and quoted identifiers before keyword scanning.

    A value such as ``'drop table'`` is data, not a statement. Masking keeps the
    blocklist from rejecting legitimate queries (and stops quoted identifiers
    from producing false positives) while the returned SQL is left untouched.
    """
    out = list(sql)
    quote: str | None = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            if ch == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    out[i] = out[i + 1] = " "
                    i += 2
                    continue
                quote = None
            out[i] = " "
        elif ch in {"'", '"'}:
            quote = ch
            out[i] = " "
        i += 1
    return "".join(out)


def limit_sql(sql: str, limit: int = 1000) -> str:
    """Wrap a query so it can never return an unbounded result set."""
    if re.search(r"\blimit\s+\d+(\s*,\s*\d+)?\b", sql, re.I):
        return sql
    return f"SELECT * FROM (\n{sql}\n) AS _atlas_q LIMIT {int(limit)}"


def _strip_comments(sql: str) -> str:
    out: list[str] = []
    i = 0
    in_single = False
    in_line_comment = False
    in_block = False
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            i += 1
            continue
        if in_block:
            if ch == "*" and nxt == "/":
                in_block = False
                i += 2
                continue
            i += 1
            continue
        if not in_single and ch == "-" and nxt == "-":
            in_line_comment = True
            i += 2
            continue
        if not in_single and ch == "/" and nxt == "*":
            in_block = True
            i += 2
            continue
        if ch == "'":
            in_single = not in_single
        out.append(ch)
        i += 1
    return "".join(out)
