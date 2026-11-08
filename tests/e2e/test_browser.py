"""Browser-level smoke, print, and accessibility tests.

These run against a real Atlas process and a real Chromium instance. They are
opt-in (``ATLAS_E2E=1``) and intentionally dependency-light: Playwright,
axe-core and pypdf are the only additions.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ARTIFACTS = Path(__file__).resolve().parents[2] / "artifacts" / "e2e"


def _goto(page, url: str) -> None:
    page.goto(url, wait_until="networkidle", timeout=60_000)


def test_landing_page_and_live_demo(page, base_url):
    _goto(page, base_url + "/")
    page.wait_for_selector("#demoForm", timeout=30_000)
    assert "Atlas" in page.title()
    assert page.locator("#dataOrb").is_visible()
    assert page.locator("#start").is_visible()

    page.fill("#demoInput", "How many rows are there?")
    page.locator("#demoForm").evaluate("form => form.requestSubmit()")
    page.wait_for_selector("#demoAnswer .answer-title", timeout=30_000)
    answer = page.inner_text("#demoAnswer").lower()
    assert "row" in answer or "records" in answer or "1" in answer


def test_landing_mobile_navigation(browser, base_url):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    try:
        _goto(page, base_url + "/")
        page.locator("#navToggle").click()
        page.wait_for_timeout(250)
        assert page.locator("#mobileMenu").is_visible()
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
        assert not page.locator("#mobileMenu").is_visible()
    finally:
        context.close()


def test_workspace_ask_palette_filters_and_trash(page, base_url, tmp_path):
    _goto(page, base_url + "/app")
    page.wait_for_selector(".page-title", timeout=30_000)
    assert page.locator(".ds-item").count() == 3

    # Command palette drives the same Ask pipeline as the composer.
    page.keyboard.press("Control+k")
    page.wait_for_selector("#cmd-input", timeout=5_000)
    page.fill("#cmd-input", "How many rows are there?")
    page.keyboard.press("Enter")
    page.wait_for_selector(".answer-card .answer-title", timeout=60_000)
    answer = page.inner_text(".answer-card").lower()
    assert "row" in answer or "record" in answer
    assert page.locator("[data-toggle-sql]").count() >= 1
    assert "q=" in page.url

    # Segment filter writes to the deep link and can be cleared.
    dimension = page.evaluate(
        """async () => {
          const id = location.hash.match(/^#\\/d\\/([^/]+)/)?.[1];
          const dataset = await (await fetch('/api/datasets/' + encodeURIComponent(id))).json();
          return dataset.profile.columns.find(
            (column) => column.role === 'dimension' && (column.top_values || []).length
          ) || null;
        }"""
    )
    assert dimension, "demo data should expose a filterable dimension"
    page.select_option("#filter-column", dimension["name"])
    page.fill("#filter-value", str(dimension["top_values"][0]["value"]))
    page.locator('[data-action="filter-add"]').click()
    page.wait_for_timeout(300)
    assert page.locator(".filter-chip").count() == 1
    assert "f=" in page.url
    page.locator('[data-action="filter-clear"]').click()
    page.wait_for_timeout(200)
    assert page.locator(".filter-chip").count() == 0

    # Soft delete, then undo from the toast.
    page.locator('[data-view="overview"]').click()
    page.wait_for_selector('[data-action="delete-dataset"]', timeout=10_000)
    page.locator('[data-action="delete-dataset"]').first.click()
    page.wait_for_selector('[data-action="confirm-delete"]', timeout=5_000)
    page.locator('[data-action="confirm-delete"]').click()
    page.wait_for_selector(".toast-action", timeout=10_000)
    page.locator(".toast-action").first.click()
    page.wait_for_timeout(1200)
    assert page.locator(".ds-item").count() == 3

    # Multi-file upload: inspect the first file, then upload both.
    first = tmp_path / "e2e_revenue.csv"
    first.write_text("date,region,revenue\n2026-01-01,North,120\n2026-01-02,South,90\n", encoding="utf-8")
    second = tmp_path / "e2e_people.csv"
    second.write_text("team,headcount\nData,4\nDesign,3\n", encoding="utf-8")
    page.locator('[data-action="upload-open"]').first.click()
    page.wait_for_selector("#file-input", state="attached", timeout=5_000)
    page.set_input_files("#file-input", [str(first), str(second)])
    page.wait_for_timeout(200)
    assert page.locator("#upload-list .upload-row").count() == 2
    page.locator('[data-action="upload-inspect"]').click()
    page.wait_for_selector("#upload-inspect .table-scroll", timeout=30_000)
    assert "header row" in page.inner_text("#upload-inspect").lower()
    page.locator('[data-action="upload-submit"]').click()
    page.wait_for_timeout(3000)
    assert page.locator(".ds-item").count() == 5

    # Theme toggle persists through a reload.
    page.locator('[data-action="theme-toggle"]').first.click()
    page.wait_for_timeout(250)
    assert page.evaluate("document.documentElement.dataset.theme") == "light"
    _goto(page, base_url + "/app")
    page.wait_for_selector(".page-title", timeout=30_000)
    assert page.evaluate("document.documentElement.dataset.theme") == "light"


def test_forecast_panels_and_report_print(page, base_url, tmp_path):
    _goto(page, base_url + "/app#/d/saas-revenue/forecast")
    page.wait_for_selector("#forecast-result .card", timeout=60_000)
    page.wait_for_timeout(1500)
    forecast = page.inner_text("#forecast-result")
    assert "Model comparison" in forecast
    assert "Rolling backtest" in forecast
    assert "Calendar effects" in forecast
    assert page.locator("#an-sensitivity").count() == 1

    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))
    _goto(page, base_url + "/api/datasets/saas-revenue/report")
    page.wait_for_selector("h1", timeout=30_000)
    assert "SaaS Revenue" in page.inner_text("body")
    external = [url for url in requests if not url.startswith(base_url) and not url.startswith("data:")]
    assert external == [], f"Report made external requests: {external}"

    page.emulate_media(media="print")
    pdf_path = ARTIFACTS / "atlas-report.pdf"
    page.pdf(path=str(pdf_path), format="A4", print_background=True)
    assert pdf_path.stat().st_size > 20_000

    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(str(pdf_path))
    assert 1 <= len(reader.pages) <= 14
    text = "\n".join((page_text or "") for page_text in (p.extract_text() for p in reader.pages))
    compact = text.lower().replace(" ", "")
    assert "saasrevenue" in compact
    assert "evidenceappendix" in compact


def _axe_violations(page, axe_script: Path) -> list[dict]:
    result = page.evaluate(
        """async () => {
          return await axe.run(document, {
            runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
            resultTypes: ['violations'],
          });
        }"""
    )
    return result.get("violations", [])


def _assert_accessible(page, axe_script: Path, label: str) -> None:
    violations = _axe_violations(page, axe_script)
    serious = [item for item in violations if item.get("impact") in {"critical", "serious"}]
    if violations:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        (ARTIFACTS / f"axe-{label}.json").write_text(
            json.dumps(violations, indent=2), encoding="utf-8"
        )
    assert not serious, (
        f"{label} has serious accessibility violations:\n"
        + "\n".join(f"- {item['id']}: {item['help']} ({item['impact']})" for item in serious)
    )


def test_accessibility_landing_and_workspace(page, base_url, axe_script):
    # add_init_script is CDP-injected, so it runs before page scripts without
    # tripping the app's own script-src CSP (unlike add_script_tag).
    page.add_init_script(path=str(axe_script))

    _goto(page, base_url + "/")
    page.wait_for_selector("#demoForm", timeout=30_000)
    page.wait_for_timeout(1400)
    _assert_accessible(page, axe_script, "landing")

    _goto(page, base_url + "/app")
    page.wait_for_selector(".page-title", timeout=30_000)
    page.wait_for_timeout(600)
    _assert_accessible(page, axe_script, "workspace")
