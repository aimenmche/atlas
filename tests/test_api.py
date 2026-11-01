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


def test_forecast_anomalies_and_insights(client):
    forecast = client.post(
        "/api/datasets/saas-revenue/forecast",
        json={"date_col": "date", "value_col": "revenue", "horizon": 6},
    )
    assert forecast.status_code == 200
    forecast_body = forecast.json()
    assert len(forecast_body["forecast"]) == 6
    assert forecast_body["model"]

    anomalies = client.get(
        "/api/datasets/saas-revenue/anomalies",
        params={"date_col": "date", "value_col": "revenue"},
    )
    assert anomalies.status_code == 200
    assert "series" in anomalies.json()

    refreshed = client.post("/api/datasets/saas-revenue/insights/refresh")
    assert refreshed.status_code == 200
    insights = refreshed.json()["insights"]
    assert insights
    assert all(item["title"] for item in insights)


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
