"""Shared Playwright fixtures for the opt-in end-to-end suite.

Run locally with::

    ATLAS_E2E=1 python -m pytest tests/e2e -q

The suite is skipped by default so the normal unit/API run stays fast and does
not require a browser. CI installs Chromium, axe-core and pypdf in the ``ui``
job.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts" / "e2e"

ENABLED = os.environ.get("ATLAS_E2E", "").lower() in {"1", "true", "yes"}

if not ENABLED:
    collect_ignore_glob = ["test_*.py"]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="session")
def base_url(tmp_path_factory):
    if not ENABLED:
        pytest.skip("Set ATLAS_E2E=1 to run browser tests.")
    data_dir = tmp_path_factory.mktemp("atlas-e2e-data")
    port = _free_port()
    log_path = data_dir / "server.log"
    log_handle = log_path.open("w", encoding="utf-8")
    env = {
        **os.environ,
        "ATLAS_DATA_DIR": str(data_dir),
        "PYTHONIOENCODING": "utf-8",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "atlas", "--port", str(port)],
        cwd=str(ROOT),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        import httpx

        deadline = time.time() + 60
        while time.time() < deadline:
            if process.poll() is not None:
                output = log_path.read_text(encoding="utf-8", errors="replace")
                raise RuntimeError(f"Atlas exited before startup:\n{output}")
            try:
                if httpx.get(url + "/api/health", timeout=2).status_code == 200:
                    break
            except Exception:
                time.sleep(0.4)
        else:
            output = log_path.read_text(encoding="utf-8", errors="replace")
            raise RuntimeError(f"Atlas did not become healthy within 60 seconds.\n{output}")
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
        log_handle.close()


@pytest.fixture(scope="session")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runner:
        instance = runner.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 980})
    page = context.new_page()
    errors: list[str] = []
    page.on(
        "console",
        lambda message: errors.append(f"console.{message.type}: {message.text}")
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    yield page
    if errors:
        page.screenshot(path=str(ARTIFACTS / "console-error.png"), full_page=True)
    context.close()
    assert not errors, "Browser errors:\n" + "\n".join(errors)


@pytest.fixture(scope="session")
def axe_script():
    candidates = [
        ROOT / "node_modules" / "axe-core" / "axe.min.js",
        ROOT / "node_modules" / "axe-core" / "axe.js",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    pytest.skip("Install axe-core (npm install) to run accessibility checks.")
