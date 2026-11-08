"""Platform-level behaviour: reports, optional auth, request IDs and JSON logs."""
from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

import atlas.app as app_module
from atlas.app import app
from atlas.logging_setup import JsonFormatter


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_report_api_options(client):
    dataset = client.get("/api/datasets/saas-revenue").json()
    email_col = next(col for col in dataset["profile"]["columns"] if col["name"] == "contact_email")
    sample_email = email_col["top_values"][0]["value"]

    response = client.get(
        "/api/datasets/saas-revenue/report",
        params={
            "download": "true",
            "title": "Board Pack",
            "brand": "Acme",
            "template": "executive",
            "sections": "read,columns,appendix",
            "redact": "true",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="atlas-saas-revenue.html"'
    )
    html = response.text
    assert "Acme report" in html
    assert "Board Pack" in html
    assert "<h2>The read</h2>" in html
    assert "Evidence appendix" in html
    assert "PII columns and sampled values were redacted" in html
    assert "•••• redacted" in html
    assert sample_email not in html

    plain = client.get(
        "/api/datasets/saas-revenue/report",
        params={"sections": "columns", "redact": "false"},
    )
    assert plain.status_code == 200
    assert "<h2>Column dictionary</h2>" in plain.text
    assert "Evidence appendix" not in plain.text
    assert "<h2>The read</h2>" not in plain.text
    assert sample_email in plain.text

    quality = client.get(
        "/api/datasets/saas-revenue/report?template=quality&sections=method"
    )
    assert quality.status_code == 200
    assert "<h2>Method &amp; provenance</h2>" in quality.text or "<h2>Method & provenance</h2>" in quality.text
    assert "<h2>Data quality</h2>" not in quality.text
    assert "<h2>Column dictionary</h2>" not in quality.text

    forecast = client.get("/api/datasets/saas-revenue/report?template=forecast")
    assert forecast.status_code == 200
    html = forecast.text
    assert "<h2>Forecast</h2>" in html
    assert "Projected periods" in html
    assert "Model comparison" in html
    assert "Holdout MAE" in html
    assert "Interval method" in html
    assert "<script" not in html.lower()
    assert "http://" not in html and "https://" not in html

    missing = client.get("/api/datasets/hr-attrition/report?sections=forecast")
    assert missing.status_code == 200
    assert "forecast" in missing.text.lower()


def test_glossary_reaches_the_column_dictionary(client):
    dataset_id = "marketing-channels"
    before = client.get(f"/api/datasets/{dataset_id}").json()
    assert before["glossary"] == {}
    updated = client.patch(
        f"/api/datasets/{dataset_id}",
        json={"glossary": {"channel": "Paid and organic acquisition source"}},
    )
    assert updated.status_code == 200

    report = client.get(
        f"/api/datasets/{dataset_id}/report", params={"sections": "columns", "redact": "false"}
    )
    assert report.status_code == 200
    assert "Paid and organic acquisition source" in report.text

    client.patch(f"/api/datasets/{dataset_id}", json={"glossary": {}})
    assert client.get(f"/api/datasets/{dataset_id}").json()["glossary"] == {}


def test_request_id_is_echoed_or_generated(client):
    supplied = client.get("/api/health", headers={"X-Request-ID": "smoke-request-1"})
    assert supplied.status_code == 200
    assert supplied.headers["x-request-id"] == "smoke-request-1"

    generated = client.get("/api/health")
    request_id = generated.headers["x-request-id"]
    assert request_id
    assert len(request_id) == 32
    assert generated.headers["content-security-policy"].startswith("default-src 'self'")


def test_auth_token_is_required_and_cookie_exchange_works(client, monkeypatch):
    monkeypatch.setattr(app_module, "AUTH_TOKEN", "test-secret-token")

    denied = client.get("/api/health")
    assert denied.status_code == 401
    assert denied.headers["www-authenticate"] == "Bearer"
    assert "bearer token is required" in denied.json()["detail"].lower()
    assert denied.headers["x-request-id"]

    bearer = client.get(
        "/api/health", headers={"Authorization": "Bearer test-secret-token"}
    )
    assert bearer.status_code == 200

    header = client.get("/api/health", headers={"X-Atlas-Token": "test-secret-token"})
    assert header.status_code == 200

    wrong = client.get("/api/health", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401

    bootstrap = client.get("/api/health?token=test-secret-token", follow_redirects=False)
    assert bootstrap.status_code == 303
    assert bootstrap.headers["location"] == "/api/health"
    cookie = bootstrap.headers["set-cookie"]
    assert "atlas_token=test-secret-token" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Max-Age=604800" in cookie

    # The exchange sets a cookie on the client; that cookie is now sufficient.
    cookie_authed = client.get("/api/health")
    assert cookie_authed.status_code == 200


def test_json_log_formatter_emits_request_fields():
    record = logging.LogRecord(
        name="atlas",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="GET /api/health 200",
        args=(),
        exc_info=None,
    )
    record.request_id = "abc123"
    record.method = "GET"
    record.path = "/api/health"
    record.status = 200
    record.ms = 4.25
    record.client = "127.0.0.1"

    payload = json.loads(JsonFormatter().format(record))
    assert payload["level"] == "info"
    assert payload["logger"] == "atlas"
    assert payload["message"] == "GET /api/health 200"
    assert payload["request_id"] == "abc123"
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/health"
    assert payload["status"] == 200
    assert payload["ms"] == 4.25
    assert payload["client"] == "127.0.0.1"
    assert "ts" in payload
