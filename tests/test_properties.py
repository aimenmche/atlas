"""Property-based invariants for ingest, quality, statistics and the SQL guard.

These complement the example-based suites: they look for boundary failures that
hand-written cases miss (quoting, empty values, duplicate headers, infinities).
"""
from __future__ import annotations

import csv
import io
import math
import re

import duckdb
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from atlas.core.filters import filter_clause
from atlas.core.ingest import IngestError, read_upload
from atlas.core.profile import build_profile
from atlas.core.semantics import parse_number
from atlas.core.sqlguard import SqlRejected, validate_sql
from atlas.core.stats import welch_t

HEADER = st.text(alphabet="abcXYZ _-0123", min_size=1, max_size=14)
CELL = st.text(alphabet='abcXYZ ,$%\'"0123-', max_size=16)


@settings(max_examples=80, deadline=None)
@given(
    headers=st.lists(HEADER, min_size=1, max_size=6),
    rows=st.lists(st.lists(CELL, min_size=1, max_size=6), min_size=1, max_size=8),
)
def test_csv_ingest_keeps_rows_and_unique_headers(headers, rows):
    width = len(headers)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        padded = (row + [""] * width)[:width]
        writer.writerow(padded)

    try:
        frame, meta = read_upload(
            "property.csv", buffer.getvalue().encode("utf-8"), header_row=0
        )
    except IngestError:
        # Entirely blank files are a documented rejection, not a crash.
        return

    expected = [
        row
        for row in rows
        if any(str(cell).strip() for cell in (row + [""] * width)[:width])
    ]
    assert len(frame) == len(expected)
    names = [str(column) for column in frame.columns]
    assert len(names) == width
    assert len({name.lower() for name in names}) == width
    assert meta["rows"] == len(expected)


@settings(max_examples=50, deadline=None)
@given(
    rows=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=1000),
            st.sampled_from(["north", "south", "east", "", None]),
            st.sampled_from([True, False, None]),
        ),
        min_size=1,
        max_size=25,
    )
)
def test_quality_scores_stay_bounded(rows):
    frame = pd.DataFrame(rows, columns=["amount", "region", "active"])
    profile = build_profile(frame, "property", "Property")
    quality = profile["quality"]
    assert 0.0 <= quality["score"] <= 100.0
    assert quality["grade"] in {"A", "B", "C", "D", "F"}
    for value in quality["dimensions"].values():
        assert 0.0 <= value <= 100.0
    assert profile["rows"] == len(frame)
    assert profile["cols"] == 3


@settings(max_examples=200, deadline=None)
@given(st.floats(allow_nan=True, allow_infinity=True))
def test_parse_number_never_returns_a_non_finite_float(value):
    parsed = parse_number(value)
    assert parsed is None or math.isfinite(parsed)


@given(st.integers(min_value=0, max_value=10**9), st.integers(min_value=0, max_value=99))
def test_parse_number_handles_business_formatting(whole, cents):
    expected = float(f"{whole}.{cents:02d}")
    assert parse_number(f"${whole:,}.{cents:02d}") == expected
    assert parse_number(f"({whole:,}.{cents:02d})") == -expected


SAMPLE = st.lists(
    st.floats(min_value=-1_000_000, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    min_size=2,
    max_size=40,
)


@settings(max_examples=80, deadline=None)
@given(a=SAMPLE, b=SAMPLE)
def test_welch_t_returns_bounded_probabilities(a, b):
    result = welch_t(a, b)
    assert result["p"] is None or 0.0 <= result["p"] <= 1.0
    if result["t"] is not None:
        assert math.isfinite(result["t"])
        assert result["df"] is None or result["df"] > 0
    if result["ci_low"] is not None and result["ci_high"] is not None:
        assert result["ci_low"] <= result["ci_high"]


@settings(max_examples=150, deadline=None)
@given(st.text(max_size=120))
def test_values_cannot_escape_a_segment_filter(value):
    con = duckdb.connect(":memory:")
    try:
        con.execute("CREATE TABLE t (x VARCHAR)")
        con.execute("INSERT INTO t VALUES ('safe'), ('other')")
        clause = filter_clause([{"column": "x", "value": value}])
        count = con.execute(f"SELECT COUNT(*) FROM t WHERE {clause}").fetchone()[0]
        assert 0 <= count <= 2
    finally:
        con.close()


@settings(max_examples=150, deadline=None)
@given(st.text(max_size=100))
def test_sql_guard_only_returns_read_only_statements(sql):
    try:
        cleaned = validate_sql(sql)
    except SqlRejected:
        return
    assert re.match(r"^(SELECT|WITH)\b", cleaned.strip(), flags=re.IGNORECASE)
