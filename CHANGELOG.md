# Changelog

All notable changes to Atlas are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [2.0.0] - 2026-11-08

### Added

- **Dataset metadata**: descriptions, case-insensitive tags (12 max), and a
  column glossary (200 terms) that flows into reports and Ask Atlas.
- **Trash and restore**: deleted datasets go to a 30-day trash with explicit
  permanent delete, startup purge, and an undo toast in the UI.
- **Segment filters**: `column = value` filters applied to Explore, Ask, and
  saved deep links by wrapping the table in a filtered subquery.
- **Comparison, cohort retention, and relationships** analytics endpoints and
  views, including a Welch t-test with a hand-written t distribution.
- **Forecast upgrades**: candidate model comparison, rolling-origin backtest,
  calibrated intervals, calendar effects, date exclusions, and anomaly
  thresholds with a sensitivity control.
- **Report studio**: custom title and brand, section toggles, four templates
  (`full`, `executive`, `quality`, `forecast`), PII redaction, glossary
  definitions, an evidence appendix, and a forecast section with inline SVG.
- **Ingest controls**: header detection and override, multi-sheet Excel
  selection, nested JSON flattening or path selection, and a pre-ingest preview.
- **Ask upgrades**: stateless multi-turn history, clarification choices on
  `422`, LLM retries with backoff, token and cost budgets, schema
  pre-validation, and a prompt-injection regression suite.
- **Workspace shell**: command palette (`Ctrl/Cmd+K`), light theme, mobile tab
  selector, saved questions, pinned insights, workspace deep links, and a
  multi-file upload queue.
- **CLI**: `serve`, `backup`, `restore`, and `watch` subcommands with safe zip
  extraction.
- **Optional auth** for non-loopback clients via `ATLAS_AUTH_TOKEN`, exchanged
  for an HttpOnly SameSite cookie, plus request IDs in `X-Request-ID`.
- **Structured logs** behind `ATLAS_LOG_JSON=1`.
- **Offline API docs**: `/openapi.json`, `scripts/export_openapi.py`, and
  `docs/api.md` (Swagger and ReDoc stay off because they load CDN assets).
- **Docs**: architecture guide, local API reference, threat model, contributor
  guide, code of conduct, issue forms, and a PR template.
- Browser security headers and a Content Security Policy for the landing page,
  workspace, and reports.
- Origin and `Sec-Fetch-Site` checks for state-changing requests.
- Upload signature validation, bounded streaming spooling, and atomic raw-file
  archiving.
- A 1200×630 social preview image, complete Open Graph/Twitter metadata, and an
  animated demo GIF.
- Dependabot configuration, coverage reporting with a 70% floor, Python 3.14 in
  the CI matrix, and UI, cross-platform, and Docker CI jobs.
- Tag-driven `release.yml` and a manual `version.yml` bump workflow backed by
  `scripts/bump_version.py`.
- Playwright end-to-end tests (opt-in with `ATLAS_E2E=1`), axe accessibility
  checks, and PDF text-extraction checks for the printable report.
- Node-based frontend tests for escaping, number formatting, chart edge cases,
  and anomaly markers.
- Property-based tests for CSV round-trips, quality bounds, number parsing,
  filter escaping, and the read-only SQL contract.

### Changed

- The landing-page boot script is now an external file so the CSP can forbid
  inline scripts.
- Uploads with unknown extensions are rejected instead of being parsed as CSV.
- Ask and Explore share one filter model, and report and forecast keep their
  own dedicated controls.
- The schema migrates in place (`_atlas_schema` v1 → v4) without losing data.
- The landing page and workspace use a single set of design tokens, including
  WCAG AA contrast for muted text.

### Fixed

- Filter values are escaped before interpolation, so a quote in a value cannot
  break out of the wrapping subquery.
- Deleted datasets return `404` from detail routes instead of leaking a partial
  profile.
- The SQL guard blocks `duckdb_settings()` and catalog/`information_schema`
  probes.
- Silenced flaky upload cleanup and stale `.part` files after failed ingests.

## [1.0.0] - 2026-11-01

### Added

- Local-first analytics workspace with Overview, Explore, Ask Atlas, Forecast,
  Quality, and Report views.
- Deterministic natural-language-to-SQL engine with a 21-case benchmark.
- Read-only DuckDB sandbox with a SQL guard, row cap, and query watchdog.
- Ingestion for CSV, TSV, JSON, Excel, and Parquet with type inference, quality
  scoring, PII detection, and messy-number handling.
- Grounded narrator, optional OpenAI-compatible model path, and self-contained
  HTML reports.
- Editorial landing page with locally bundled fonts, an animated instrument,
  and a live Ask Atlas demo.
- 50 pytest cases and green CI on Python 3.11, 3.12, and 3.13.
