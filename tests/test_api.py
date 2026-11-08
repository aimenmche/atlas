"""End-to-end API tests against a throwaway Atlas data directory."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from atlas.app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_landing_and_app_shell_routes(client):
    landing = client.get("/")
    assert landing.status_code == 200
    assert landing.headers["content-type"].startswith("text/html")
    assert "Atlas — your data has a shape" in landing.text
    assert 'href="/app"' in landing.text
    assert "/static/landing.js" in landing.text
    assert 'property="og:image"' in landing.text
    assert "/static/og-atlas.png" in landing.text
    assert 'name="twitter:card"' in landing.text

    shell = client.get("/app")
    assert shell.status_code == 200
    assert shell.headers["content-type"].startswith("text/html")
    assert "<title>Atlas · data intelligence</title>" in shell.text
    assert "/static/app.js" in shell.text

    redirect = client.get("/app/", follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "/app"

    for path in (
        "/static/landing.css",
        "/static/landing.js",
        "/static/landing-preview.png",
        "/static/og-atlas.png",
        "/static/boot.js",
        "/static/fonts/instrument-serif-regular.woff2",
        "/static/fonts/space-grotesk.woff2",
        "/static/fonts/LICENSE.txt",
    ):
        assert client.get(path).status_code == 200, path


def test_health_and_seeded_datasets(client):
    health = client.get("/api/health").json()
    assert health["ok"] is True
    assert health["datasets"] == 3
    assert health["rows"] > 12_000
    assert health["llm"]["enabled"] is False

    listing = client.get("/api/datasets").json()
    ids = {item["id"] for item in listing["datasets"]}
    assert ids == {"saas-revenue", "marketing-channels", "hr-attrition"}
    names = {item["name"] for item in listing["datasets"]}
    assert names == {"SaaS Revenue", "Marketing Channels", "HR Attrition"}


def test_detail_preview_and_uniqueness(client):
    detail = client.get("/api/datasets/saas-revenue").json()
    assert detail["rows"] == 10_242
    assert detail["cols"] == 13
    assert detail["profile"]["time"]["column"] == "date"
    issue_ids = [i["id"] for i in detail["profile"]["quality"]["issues"]]
    assert len(issue_ids) == len(set(issue_ids))

    preview = client.get("/api/datasets/saas-revenue/preview?limit=5").json()
    assert len(preview["rows"]) == 5
    assert preview["columns"][0] == "date"


def test_read_only_query(client):
    response = client.post(
        "/api/datasets/saas-revenue/query",
        json={
            "sql": (
                'SELECT region, SUM(revenue) AS revenue '
                'FROM "ds_saasrevenue" GROUP BY region ORDER BY revenue DESC'
            )
        },
    )
    assert response.status_code == 200
    result = response.json()
    # The demo data is deliberately messy: raw grouping exposes spelling drift,
    # which the quality report flags and the NL engine normalizes.
    assert result["row_count"] == 7
    assert result["rows"][0][1] > result["rows"][1][1]


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE ds_saasrevenue",
        "SELECT 1; DROP TABLE ds_saasrevenue",
        "SELECT * FROM read_csv_auto('C:/Windows/win.ini')",
    ],
)
def test_query_sandbox_rejects_unsafe_sql(client, sql):
    response = client.post("/api/datasets/saas-revenue/query", json={"sql": sql})
    assert response.status_code == 400


def test_ask_and_stream(client):
    question = {"question": "Which region has the highest revenue?"}

    answer = client.post("/api/datasets/saas-revenue/ask", json=question)
    assert answer.status_code == 200
    payload = answer.json()
    assert payload["chart"]["type"] == "bar"
    assert payload["result"]["row_count"] == 4
    assert "North America" in payload["narrative"]
    assert payload["confidence"]["label"] in {"high", "medium"}
    assert payload["trace"][-1]["stage"] == "finish"

    with client.stream(
        "POST", "/api/datasets/saas-revenue/ask/stream", json=question
    ) as stream:
        assert stream.status_code == 200
        body = "".join(stream.iter_text())
    assert "event: step" in body
    assert "event: answer" in body
    assert '"stage": "finish"' in body


def test_ask_refuses_ambiguous_question(client):
    response = client.post(
        "/api/datasets/saas-revenue/ask",
        json={"question": "Show revenue by plan and segment"},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"]
    assert detail["hint"]


def test_upload_rename_and_delete(client):
    csv = (
        b"date,region,revenue,seats\n"
        b"2025-01-01,EMEA,\"$1,200.50\",10\n"
        b"2025-01-02,APAC,\"$900.00\",7\n"
        b"2025-01-03,EMEA,\"$1,500.25\",12\n"
    )
    created = client.post(
        "/api/datasets",
        files={"file": ("tiny_set.csv", csv, "text/csv")},
        data={"name": "Tiny Set"},
    )
    assert created.status_code == 201
    upload = created.json()
    assert upload["id"] == "tiny-set"
    assert upload["time"]["column"] == "date"

    detail = client.get("/api/datasets/tiny-set").json()
    assert detail["rows"] == 3
    columns = {c["name"]: c for c in detail["profile"]["columns"]}
    assert columns["revenue"]["semantic"] == "currency"
    assert columns["date"]["role"] == "time"

    renamed = client.patch("/api/datasets/tiny-set", json={"name": "Tiny Set Renamed"})
    assert renamed.status_code == 200
    assert client.get("/api/datasets/tiny-set").json()["name"] == "Tiny Set Renamed"

    deleted = client.delete("/api/datasets/tiny-set")
    assert deleted.status_code == 200
    assert client.get("/api/datasets/tiny-set").status_code == 404


def test_trash_restore_and_permanent_delete_lifecycle(client):
    csv = b"date,region,revenue\n2025-01-01,EMEA,100\n2025-01-02,APAC,200\n"
    created = client.post(
        "/api/datasets",
        files={"file": ("recoverable.csv", csv, "text/csv")},
        data={"name": "Recoverable Set"},
    )
    assert created.status_code == 201
    dataset_id = created.json()["id"]

    soft = client.delete(f"/api/datasets/{dataset_id}")
    assert soft.status_code == 200
    assert soft.json()["trashed"] is True
    assert soft.json()["restore_days"] == 30
    assert client.get(f"/api/datasets/{dataset_id}").status_code == 404

    trash = client.get("/api/trash").json()
    item = next(row for row in trash["datasets"] if row["id"] == dataset_id)
    assert item["deleted_at"]

    restored = client.post(f"/api/datasets/{dataset_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["dataset"]["id"] == dataset_id
    assert client.get(f"/api/datasets/{dataset_id}").status_code == 200
    assert all(row["id"] != dataset_id for row in client.get("/api/trash").json()["datasets"])

    # A second soft delete can be purged explicitly from the trash view.
    client.delete(f"/api/datasets/{dataset_id}")
    purged = client.delete(f"/api/trash/{dataset_id}")
    assert purged.status_code == 200
    assert purged.json()["permanent"] is True
    assert client.get(f"/api/datasets/{dataset_id}").status_code == 404
    assert all(row["id"] != dataset_id for row in client.get("/api/trash").json()["datasets"])

    created = client.post(
        "/api/datasets",
        files={"file": ("hard-delete.csv", csv, "text/csv")},
        data={"name": "Hard Delete Set"},
    )
    hard_id = created.json()["id"]
    hard = client.delete(f"/api/datasets/{hard_id}", params={"permanent": True})
    assert hard.status_code == 200
    assert hard.json()["permanent"] is True
    assert client.get(f"/api/datasets/{hard_id}").status_code == 404


def test_query_applies_segment_filters_safely(client):
    total = client.get("/api/datasets/saas-revenue").json()["rows"]
    filtered = client.post(
        "/api/datasets/saas-revenue/query",
        json={
            "sql": "SELECT COUNT(*) AS n FROM {table}",
            "filters": [{"column": "region", "value": "EMEA"}],
        },
    )
    assert filtered.status_code == 200
    emea = filtered.json()["rows"][0][0]
    assert 0 < emea < total

    injected = client.post(
        "/api/datasets/saas-revenue/query",
        json={
            "sql": "SELECT COUNT(*) AS n FROM {table}",
            "filters": [{"column": "region", "value": "EMEA' OR '1'='1"}],
        },
    )
    assert injected.status_code == 200
    assert injected.json()["rows"][0][0] == 0

    blank = client.post(
        "/api/datasets/saas-revenue/query",
        json={"sql": "SELECT 1 AS n", "filters": [{"column": "region", "value": ""}]},
    )
    assert blank.status_code == 200
    assert blank.json()["rows"][0][0] == 1


def test_dataset_description_and_tags(client):
    csv = b"date,region,revenue\n2025-01-01,EMEA,100\n2025-01-02,APAC,200\n"
    created = client.post(
        "/api/datasets",
        files={"file": ("tagged.csv", csv, "text/csv")},
        data={"name": "Tagged Set"},
    )
    assert created.status_code == 201
    dataset_id = created.json()["id"]

    updated = client.patch(
        f"/api/datasets/{dataset_id}",
        json={
            "name": "Tagged Set",
            "description": "Monthly revenue by region.",
            "tags": ["Finance", "finance", " monthly "],
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["description"] == "Monthly revenue by region."
    assert body["tags"] == ["Finance", "monthly"]

    detail = client.get(f"/api/datasets/{dataset_id}").json()
    assert detail["description"] == "Monthly revenue by region."
    assert detail["tags"] == ["Finance", "monthly"]
    listing = client.get("/api/datasets").json()["datasets"]
    item = next(item for item in listing if item["id"] == dataset_id)
    assert item["tags"] == ["Finance", "monthly"]

    assert client.patch(f"/api/datasets/{dataset_id}", json={}).status_code == 400
    too_many = client.patch(
        f"/api/datasets/{dataset_id}",
        json={"tags": [f"tag-{i}" for i in range(13)]},
    )
    assert too_many.status_code == 400

    glossary = client.patch(
        f"/api/datasets/{dataset_id}",
        json={
            "glossary": {
                "revenue": "  Net recognised revenue  ",
                "region": "Sales territory",
            }
        },
    )
    assert glossary.status_code == 200
    assert glossary.json()["glossary"] == {
        "revenue": "Net recognised revenue",
        "region": "Sales territory",
    }
    detail = client.get(f"/api/datasets/{dataset_id}").json()
    assert detail["glossary"]["revenue"] == "Net recognised revenue"

    unknown = client.patch(
        f"/api/datasets/{dataset_id}",
        json={"glossary": {"not_a_column": "Nope"}},
    )
    assert unknown.status_code == 400
    assert "Unknown column" in unknown.json()["detail"]

    too_long = client.patch(
        f"/api/datasets/{dataset_id}",
        json={"glossary": {"revenue": "x" * 281}},
    )
    assert too_long.status_code == 400

    cleared = client.patch(
        f"/api/datasets/{dataset_id}",
        json={"glossary": {"revenue": ""}},
    )
    assert cleared.status_code == 200
    assert cleared.json()["glossary"] == {}

    client.delete(f"/api/datasets/{dataset_id}")


def test_forecast_anomalies_and_insights(client):
    forecast = client.post(
        "/api/datasets/saas-revenue/forecast",
        json={
            "date_col": "date",
            "value_col": "revenue",
            "horizon": 6,
            "calendar": True,
            "exclude": "2025-12-25",
            "include_anomalies": True,
        },
    )
    assert forecast.status_code == 200
    forecast_body = forecast.json()
    assert len(forecast_body["forecast"]) == 6
    assert forecast_body["model"]
    assert forecast_body["candidates"]
    assert forecast_body["backtest"]
    assert forecast_body["interval"]["points"]
    assert forecast_body["interval"]["method"]
    assert forecast_body["calendar"]["note"]
    assert forecast_body["excluded_dates"] == ["2025-12-25"]
    assert isinstance(forecast_body["anomalies"], list)

    anomalies = client.get(
        "/api/datasets/saas-revenue/anomalies",
        params={"date_col": "date", "value_col": "revenue"},
    )
    assert anomalies.status_code == 200
    assert "series" in anomalies.json()

    sensitive = client.get(
        "/api/datasets/saas-revenue/anomalies",
        params={
            "date_col": "date",
            "value_col": "revenue",
            "sensitivity": "high",
            "exclude": "2025-12-25",
        },
    )
    assert sensitive.status_code == 200
    sensitive_body = sensitive.json()
    assert sensitive_body["sensitivity"] == "high"
    assert sensitive_body["threshold"] == 2.5
    assert sensitive_body["excluded_dates"] == ["2025-12-25"]
    assert sensitive_body["count"] == len(sensitive_body["anomalies"])

    refreshed = client.post("/api/datasets/saas-revenue/insights/refresh")
    assert refreshed.status_code == 200
    insights = refreshed.json()["insights"]
    assert insights
    assert all(item["title"] for item in insights)


def test_compare_cohort_and_relationships(client):
    compare = client.post(
        "/api/datasets/saas-revenue/compare",
        json={
            "date_col": "date",
            "value_col": "revenue",
            "grain": "month",
            "dimension": "region",
        },
    )
    assert compare.status_code == 200
    body = compare.json()
    assert body["current_period"] and body["previous_period"]
    assert body["waterfall"][0]["kind"] == "start"
    assert body["waterfall"][-1]["kind"] == "end"
    assert abs(sum(row["delta"] for row in body["contributions"]) - body["delta"]) < 0.01
    assert body["significance"]["n_current"] >= 1

    cohort = client.post(
        "/api/datasets/saas-revenue/cohorts",
        json={
            "entity_col": "account_id",
            "date_col": "date",
            "value_col": "revenue",
            "grain": "month",
            "periods": 6,
        },
    )
    assert cohort.status_code == 200
    cohort_body = cohort.json()
    assert cohort_body["cohorts"]
    assert len(cohort_body["average"]) == 6

    matrix = client.post(
        "/api/datasets/saas-revenue/relationships",
        json={"mode": "matrix", "columns": ["revenue", "seats", "customers"]},
    )
    assert matrix.status_code == 200
    matrix_body = matrix.json()
    assert len(matrix_body["matrix"]) == 3
    assert matrix_body["matrix"][0][0] == 1.0

    lag = client.post(
        "/api/datasets/saas-revenue/relationships",
        json={
            "mode": "lag",
            "date_col": "date",
            "x_col": "revenue",
            "y_col": "seats",
            "grain": "month",
            "max_lag": 3,
        },
    )
    assert lag.status_code == 200
    lag_body = lag.json()
    assert len(lag_body["rows"]) == 7
    assert lag_body["same_period_r"] is not None


def test_report_is_self_contained_html(client):
    response = client.get("/api/datasets/saas-revenue/report")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert "<html" in html.lower()
    assert "SaaS Revenue" in html
    assert "<svg" in html
    assert "EVIDENCE" in html.upper()


def test_settings_roundtrip(client):
    public = client.get("/api/settings").json()
    assert public["provider"] == "none"
    assert public["llm_enabled"] is False

    updated = client.put(
        "/api/settings",
        json={
            "provider": "none",
            "model": "",
            "base_url": "",
            "api_key": "",
            "temperature": 0.2,
            "query_timeout": 8.0,
            "row_limit": 1000,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["llm_enabled"] is False


def test_missing_dataset_returns_404(client):
    assert client.get("/api/datasets/nope").status_code == 404
    assert client.post("/api/datasets/nope/query", json={"sql": "SELECT 1"}).status_code == 404
    assert client.delete("/api/datasets/nope").status_code == 404
