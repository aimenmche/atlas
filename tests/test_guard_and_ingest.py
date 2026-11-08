"""The two safety boundaries: the SQL sandbox and the ingest parser."""
from __future__ import annotations

import pytest

from atlas.core.ingest import IngestError, inspect_upload, read_upload
from atlas.core.semantics import parse_number
from atlas.core.sqlguard import SqlRejected, limit_sql, validate_sql


def test_validate_accepts_read_only_queries():
    assert validate_sql("SELECT 1") == "SELECT 1"
    assert validate_sql("  WITH x AS (SELECT 1) SELECT * FROM x;  ") == (
        "WITH x AS (SELECT 1) SELECT * FROM x"
    )
    assert validate_sql("SELECT 'drop table customers' AS note") == (
        "SELECT 'drop table customers' AS note"
    )
    assert validate_sql("SELECT 'a;b' AS note") == "SELECT 'a;b' AS note"
    assert validate_sql('SELECT "update" FROM t') == 'SELECT "update" FROM t'


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "DROP TABLE customers",
        "SELECT 1; DROP TABLE customers",
        "INSERT INTO customers VALUES (1)",
        "ATTACH 'evil.db'",
        "SELECT * FROM read_csv_auto('C:/secret.csv')",
        "SELECT current_setting('home_directory')",
        "PRAGMA database_list",
        "COPY customers TO 'out.csv'",
    ],
)
def test_validate_rejects_unsafe_sql(sql):
    with pytest.raises(SqlRejected):
        validate_sql(sql)


def test_validate_ignores_comments_but_still_checks_code():
    assert validate_sql("-- a note\nSELECT 1") == "SELECT 1"
    with pytest.raises(SqlRejected):
        validate_sql("/* hidden */ DELETE FROM customers")


def test_limit_sql_wraps_only_when_needed():
    wrapped = limit_sql("SELECT * FROM t", limit=50)
    assert "LIMIT 50" in wrapped and wrapped.startswith("SELECT * FROM (")

    explicit = "SELECT * FROM t LIMIT 10"
    assert limit_sql(explicit, limit=50) == explicit


def test_parse_number_business_formats():
    assert parse_number("$1,234.50") == pytest.approx(1234.50)
    assert parse_number("(12.4)") == pytest.approx(-12.4)
    assert parse_number("7.2%") == pytest.approx(7.2)
    assert parse_number("1 234") == pytest.approx(1234.0)
    assert parse_number("n/a") is None


MESSY_CSV = b"""id,Full Name,amount,rate,when,active
1, Ada Lovelace ,"$1,234.50",7.2%,2025-01-03,yes
2,Grace Hopper,($200.00),3.5%,2025-02-14,no
3,Alan Turing,"$0.00",,2025-03-01,yes
"""


def test_read_upload_cleans_messy_csv():
    frame, meta = read_upload("messy.csv", MESSY_CSV)

    assert list(frame.columns) == ["id", "Full Name", "amount", "rate", "when", "active"]
    assert frame["Full Name"].tolist() == ["Ada Lovelace", "Grace Hopper", "Alan Turing"]
    assert frame["amount"].tolist() == pytest.approx([1234.5, -200.0, 0.0])
    assert frame["rate"].iloc[0] == pytest.approx(7.2)
    assert str(frame["when"].dtype).startswith("datetime64")
    assert frame["active"].tolist() == [True, False, True]
    assert meta["format"] == "csv"
    assert any("Inferred types" in note for note in meta["notes"])


def test_read_upload_semicolon_delimiter():
    frame, meta = read_upload("eu.csv", b"date;region;revenue\n2025-01-01;EMEA;100\n")
    assert list(frame.columns) == ["date", "region", "revenue"]
    assert len(frame) == 1
    assert meta["delimiter"] == ";"


def test_read_upload_rejects_empty_and_single_column_garbage():
    with pytest.raises(IngestError):
        read_upload("empty.csv", b"")
    with pytest.raises(IngestError):
        read_upload("empty.csv", b"\n\n\n")


def test_header_row_is_detected_below_a_title_row():
    payload = (
        b"Quarterly revenue export\n"
        b"region,revenue,orders\n"
        b"EMEA,1200,14\n"
        b"APAC,900,11\n"
    )
    frame, meta = read_upload("titled.csv", payload)
    assert list(frame.columns) == ["region", "revenue", "orders"]
    assert len(frame) == 2
    assert meta["header_row"] == 1
    assert any("header on row 2" in note for note in meta["notes"])


def test_header_row_can_be_disabled():
    frame, meta = read_upload(
        "no-header.csv",
        b"EMEA,1200\nAPAC,900\n",
        header_row=-1,
    )
    assert list(frame.columns) == ["column_1", "column_2"]
    assert len(frame) == 2
    assert meta["header_row"] == -1


def test_nested_json_is_flattened_and_paths_are_listed():
    payload = (
        b'{"data": [{"id": 1, "customer": {"name": "Ada", "tier": "pro"}, '
        b'"tags": ["a", "b"]}]}'
    )
    frame, meta = read_upload("nested.json", payload)
    assert "customer.name" in frame.columns
    assert "customer.tier" in frame.columns
    assert frame["customer.name"].iloc[0] == "Ada"
    assert frame["tags"].iloc[0].startswith("[")
    assert meta["nested"] is True
    assert any("flattened" in note for note in meta["notes"])


def test_json_path_can_select_a_nested_records_array():
    payload = b'{"result": {"rows": [{"a": 1}, {"a": 2}]}}'
    frame, meta = read_upload("wrapped.json", payload, json_path="result.rows")
    assert list(frame.columns) == ["a"]
    assert len(frame) == 2
    assert meta["json_path"] == "result.rows"


def test_inspect_upload_reports_header_and_preview():
    result = inspect_upload(
        "report.csv",
        b"Monthly report\nregion,revenue\nEMEA,1200\nAPAC,900\n",
    )
    assert result["format"] == "csv"
    assert result["header_row"] == 1
    assert result["headers"] == ["region", "revenue"]
    assert result["preview"][0] == ["EMEA", "1200"]


def test_excel_sheets_can_be_listed_and_selected(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "book.xlsx"
    workbook = openpyxl.Workbook()
    first = workbook.active
    first.title = "Summary"
    first.append(["region", "revenue"])
    first.append(["EMEA", 1200])
    second = workbook.create_sheet("Detail")
    second.append(["customer", "amount"])
    second.append(["Ada", 99])
    second.append(["Grace", 88])
    workbook.save(path)

    result = inspect_upload("book.xlsx", path.read_bytes())
    assert [sheet["name"] for sheet in result["sheets"]] == ["Summary", "Detail"]
    assert result["sheets"][0]["rows"] == 2

    frame, meta = read_upload("book.xlsx", path.read_bytes(), sheet="Detail")
    assert list(frame.columns) == ["customer", "amount"]
    assert len(frame) == 2
    assert meta["sheet"] == "Detail"
    assert any("2 sheets" in note for note in meta["notes"])
