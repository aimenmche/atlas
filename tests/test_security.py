"""Security headers, origin checks, and upload signature tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from atlas.app import app
from atlas.config import RAW_DIR


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_security_headers_on_pages_and_api(client):
    for path in ("/", "/app", "/api/health"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "SAMEORIGIN"
        assert response.headers["referrer-policy"] == "no-referrer"
        csp = response.headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "frame-ancestors 'self'" in csp
        assert "object-src 'none'" in csp
        assert "upgrade-insecure-requests" not in csp


def test_cross_origin_mutation_is_rejected(client):
    response = client.post(
        "/api/settings",
        json={"provider": "none"},
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403
    assert "Cross-site" in response.json()["detail"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_cross_site_fetch_metadata_is_rejected(client):
    response = client.put(
        "/api/settings",
        json={"provider": "none"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 403


def test_same_origin_and_cli_mutations_are_allowed(client):
    # TestClient's base URL is http://testserver.
    same = client.put(
        "/api/settings",
        json={"provider": "none"},
        headers={"Origin": "http://testserver"},
    )
    assert same.status_code == 200
    cli = client.put("/api/settings", json={"provider": "none"})
    assert cli.status_code == 200


def test_loopback_alias_is_treated_as_same_origin(client):
    response = client.put(
        "/api/settings",
        json={"provider": "none"},
        headers={"Origin": "http://127.0.0.1:8000", "Host": "localhost:8000"},
    )
    assert response.status_code == 200


def test_renamed_executable_is_rejected_before_parsing(client):
    before = {p.name for p in RAW_DIR.glob("*")} if RAW_DIR.exists() else set()
    response = client.post(
        "/api/datasets",
        files={"file": ("totally-safe.csv", b"MZ\x90\x00\x03\x00\x00\x00", "text/csv")},
        data={"name": "Renamed Binary"},
    )
    assert response.status_code == 400
    assert "text-delimited" in response.json()["detail"]
    after = {p.name for p in RAW_DIR.glob("*")} if RAW_DIR.exists() else set()
    assert after == before


def test_unsupported_extension_is_rejected(client):
    response = client.post(
        "/api/datasets",
        files={"file": ("payload.exe", b"not really an exe", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_json_must_start_with_array_or_object(client):
    response = client.post(
        "/api/datasets",
        files={"file": ("data.json", b"42", "application/json")},
    )
    assert response.status_code == 400
    assert "array or an object" in response.json()["detail"]


def test_utf16_csv_is_accepted(client):
    text = "date,region,revenue\n2025-01-01,EMEA,100\n2025-01-02,APAC,200\n"
    payload = text.encode("utf-16")
    response = client.post(
        "/api/datasets",
        files={"file": ("utf16.csv", payload, "text/csv")},
        data={"name": "UTF16 Set"},
    )
    assert response.status_code == 201
    dataset_id = response.json()["id"]
    detail = client.get(f"/api/datasets/{dataset_id}").json()
    assert detail["rows"] == 2
    client.delete(f"/api/datasets/{dataset_id}")


def test_streaming_upload_limit_is_enforced_and_leaves_no_partials(client, monkeypatch):
    import atlas.app as app_module

    before = {p.name for p in RAW_DIR.glob("*")} if RAW_DIR.exists() else set()
    monkeypatch.setattr(app_module, "MAX_UPLOAD_BYTES", 64)
    payload = b"date,region,revenue\n" + b"2025-01-01,EMEA,100\n" * 20
    response = client.post(
        "/api/datasets",
        files={"file": ("too-big.csv", payload, "text/csv")},
        data={"name": "Too Big"},
    )
    assert response.status_code == 413
    assert "upload limit" in response.json()["detail"].lower()
    after = {p.name for p in RAW_DIR.glob("*")} if RAW_DIR.exists() else set()
    assert after == before
    assert not list(RAW_DIR.glob(".upload-*.part"))


def test_streaming_inspect_limit_is_enforced(client, monkeypatch):
    import atlas.app as app_module

    monkeypatch.setattr(app_module, "MAX_UPLOAD_BYTES", 32)
    response = client.post(
        "/api/datasets/inspect",
        files={"file": ("too-big.csv", b"date,value\n" + b"2025-01-01,1\n" * 10, "text/csv")},
    )
    assert response.status_code == 413
    assert not list(RAW_DIR.glob(".upload-*.part"))


def test_uploaded_raw_file_is_archived_atomically(client):
    payload = b"date,region,revenue\n2025-01-01,EMEA,100\n"
    response = client.post(
        "/api/datasets",
        files={"file": ("archive_check.csv", payload, "text/csv")},
        data={"name": "Archive Check"},
    )
    assert response.status_code == 201
    dataset_id = response.json()["id"]
    archived = RAW_DIR / f"{dataset_id}.csv"
    assert archived.exists()
    assert archived.read_bytes() == payload
    assert not list(RAW_DIR.glob(".upload-*.part"))
    client.delete(f"/api/datasets/{dataset_id}", params={"permanent": True})
    assert not archived.exists()
