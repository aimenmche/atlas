"""Deterministic NL→SQL and the narration built on top of its results."""
from __future__ import annotations

import duckdb
import pytest

from atlas.core.agent import build_chart
from atlas.core.narrator import narrate
from atlas.core.nlsql import parse_question
from atlas.core.semantics import detect

TABLE = "ds_saasrevenue"


@pytest.fixture()
def con(saas_frame):
    connection = duckdb.connect(":memory:")
    connection.register(TABLE, saas_frame)
    yield connection
    connection.close()


def _run(con, parsed):
    rel = con.execute(parsed["sql"])
    columns = [d[0] for d in rel.description]
    rows = rel.fetchall()
    return {"columns": columns, "rows": rows, "row_count": len(rows)}


def test_grouped_aggregate_uses_measure_not_row_count(saas_profile):
    parsed = parse_question("Which region has the highest revenue?", saas_profile, TABLE)
    assert parsed is not None
    assert parsed["intent"] == "group_by"
    assert 'SUM("revenue")' in parsed["sql"]
    assert "COUNT(*)" not in parsed["sql"]


def test_grouped_aggregate_executes_and_normalizes_labels(con, saas_profile):
    parsed = parse_question("Which region has the highest revenue?", saas_profile, TABLE)
    result = _run(con, parsed)
    labels = {row[0] for row in result["rows"]}
    assert labels == {"APAC", "EMEA", "LATAM", "North America"}
    assert len(result["rows"]) == 4


def test_scalar_extremes_and_median(saas_profile):
    highest = parse_question("What is the highest revenue?", saas_profile, TABLE)
    assert 'MAX("revenue")' in highest["sql"]

    lowest = parse_question("What is the lowest revenue?", saas_profile, TABLE)
    assert 'MIN("revenue")' in lowest["sql"]

    median = parse_question("What's the median revenue?", saas_profile, TABLE)
    assert 'MEDIAN("revenue")' in median["sql"]
    assert median["title"] == "Median Revenue"


def test_two_measure_comparison_becomes_scatter(saas_profile):
    parsed = parse_question("Compare revenue and seats", saas_profile, TABLE)
    assert parsed["intent"] == "comparison"
    assert parsed["chart_type"] == "scatter"
    assert '"revenue"' in parsed["sql"] and '"seats"' in parsed["sql"]


def test_trend_uses_monthly_grain(saas_profile):
    parsed = parse_question("How has revenue changed over time?", saas_profile, TABLE)
    assert parsed["intent"] == "trend"
    assert parsed["chart_type"] == "line"
    assert "date_trunc('month'" in parsed["sql"]
    assert parsed["grain"] == "month"


def test_count_by_dimension(saas_profile):
    parsed = parse_question("What is the row count by region?", saas_profile, TABLE)
    assert parsed["intent"] == "count_by"
    assert "COUNT(*)" in parsed["sql"]
    assert "GROUP BY label" in parsed["sql"]


def test_time_rank_returns_pretty_labels_and_narrative(con, saas_profile):
    question = "Which month had the highest revenue?"
    parsed = parse_question(question, saas_profile, TABLE)
    assert parsed["intent"] == "time_rank"
    assert parsed["grain"] == "month"

    result = _run(con, parsed)
    assert len(result["rows"]) == 21

    narrative = narrate(question, parsed, result, saas_profile)
    assert "had the highest revenue" in narrative["narrative"]
    assert " across 21 months." in narrative["narrative"]
    assert "T00:00:00" not in narrative["narrative"]

    chart = build_chart(parsed, result, saas_profile)
    assert chart["type"] == "bar"
    assert chart["labels"][0] == "Aug 2026"
    assert all("T00:00:00" not in label for label in chart["labels"])


def test_refuses_ambiguous_or_unknown_requests(saas_profile):
    assert parse_question("Show revenue by plan and segment", saas_profile, TABLE) is None
    assert parse_question("Show revenue by industry", saas_profile, TABLE) is None
    assert parse_question("forecast revenue next 6 months", saas_profile, TABLE) is None


def test_forecast_question_without_time_words_is_refused(saas_profile):
    assert parse_question("Project revenue for the next quarter", saas_profile, TABLE) is None


def test_semantics_taxonomy(saas_frame):
    expectations = {
        "date": ("date", "time", False),
        "revenue": ("currency", "measure", False),
        "seats": ("count", "measure", False),
        "account_id": ("id", "identifier", False),
        "contact_email": ("email", "identifier", True),
        "region": ("category", "dimension", False),
    }
    for column, (semantic, role, pii) in expectations.items():
        found = detect(column, saas_frame[column], saas_frame[column].dtype)
        assert (found["semantic"], found["role"], found["pii"]) == (semantic, role, pii)


def test_profile_marks_quality_issue_ids_unique(saas_profile):
    quality = saas_profile["quality"]
    ids = [issue["id"] for issue in quality["issues"]]
    assert len(ids) == len(set(ids)), "quality issues must not be duplicated"
    assert quality["dimensions"]["completeness"] > 95
