# Architecture

Atlas is one local process with two browser surfaces. There is no build step, no
message queue, no external database, and no telemetry. The architecture is
optimised for a single analyst on a laptop who needs every number to be
reproducible.

```
┌───────────────────────────────────────────────────────────────────────────┐
│ Browser                                                                   │
│  /              landing.html + landing.css + landing.js + charts.js       │
│  /app           index.html   + styles.css  + app.js      + charts.js      │
│  report         self-contained HTML + inline SVG + inline CSS             │
└───────────────────────────────┬───────────────────────────────────────────┘
                                │ same-origin HTTP, SSE for Ask
┌───────────────────────────────▼───────────────────────────────────────────┐
│ FastAPI (atlas/app.py)                                                    │
│  security middleware → auth/origin checks → route → JSON/HTML/SSE         │
│  request IDs, structured logs, CSP and browser hardening headers          │
└───────────────┬──────────────────────────────┬────────────────────────────┘
                │                              │
┌───────────────▼──────────────┐  ┌────────────▼───────────────────────────┐
│ Analysis core (atlas/core)   │  │ Store (atlas/core/store.py)            │
│  ingest → profile → quality  │  │  DuckDB file, one table per dataset    │
│  nlsql / agent / llm         │  │  `_atlas_datasets` registry            │
│  sqlguard → DuckDB sandbox   │  │  `_atlas_schema` migration ledger      │
│  stats / compare / cohort    │  │  raw upload archive under data/raw     │
│  forecast / anomaly          │  └────────────────────────────────────────┘
│  narrator / report           │
└──────────────────────────────┘
```

## Process model

`atlas` starts Uvicorn with a single FastAPI application. On startup the app:

1. Creates the data directory (`ATLAS_DATA_DIR`, default `./data`).
2. Removes stale `.part` upload files left by an interrupted request.
3. Opens DuckDB and applies schema migrations.
4. Purges trash items older than 30 days.
5. Seeds the three synthetic demo datasets if the store is empty.
6. Serves until shutdown, then closes the DuckDB connection.

The CLI also exposes `backup`, `restore`, and `watch` subcommands. `watch` is a
separate short-lived client that posts new or changed files to a running Atlas
service; it does not open the database itself.

## Package map

| Module | Responsibility |
| --- | --- |
| `atlas/app.py` | Routes, middleware, payload models, request validation, demo seeding. |
| `atlas/config.py` | Data paths, settings file, `.env` loading, upload limits. |
| `atlas/security.py` | CSP and browser headers, Origin/`Sec-Fetch-Site` checks, optional token auth and cookie exchange. |
| `atlas/logging_setup.py` | Human-readable or `ATLAS_LOG_JSON=1` newline-delimited JSON logs. |
| `atlas/core/ingest.py` | CSV/TSV/JSON/Excel/Parquet readers, signature checks, header detection, nested JSON flattening, multi-sheet selection, cleaning. |
| `atlas/core/profile.py` | Column inference, semantic types, time coverage, correlations, quality call. |
| `atlas/core/quality.py` | Completeness, uniqueness, consistency, validity; issues and grade. |
| `atlas/core/nlsql.py` | Deterministic question parser and SQL builder. No model required. |
| `atlas/core/agent.py` | Ask pipeline: deterministic plan, optional LLM proposal, schema validation, execution, clarification. |
| `atlas/core/llm.py` | OpenAI-compatible client, retries/backoff, token and cost budgets. |
| `atlas/core/sqlguard.py` | Single read-only statement, forbidden functions/catalog access, row limit, watchdog timeout. |
| `atlas/core/store.py` | DuckDB lifecycle, migrations, dataset registry, query execution, trash, raw archive. |
| `atlas/core/stats.py` | Dependency-free normal/t/F/chi-square tails, correlation, Welch tests, OLS, robust z. |
| `atlas/core/compare.py`, `cohort.py`, `relationships.py` | Period comparison with waterfall and significance, cohort retention, correlation/lag explorer. |
| `atlas/core/forecast.py` | Candidate models, rolling-origin backtest, interval calibration, calendar effects, excluded dates. |
| `atlas/core/anomaly.py` | Robust-z anomaly scan with sensitivity levels and exclusions. |
| `atlas/core/narrator.py` | Number-grounded prose. LLM text is rejected if it introduces unsupported numbers. |
| `atlas/core/report.py` | Self-contained HTML report, templates, section toggles, PII redaction, evidence appendix. |
| `atlas/static/*` | Landing page, workspace, charts, styles, bundled fonts. No runtime dependency. |

## Ask pipeline

```
question + history + filters
        │
        ▼
deterministic parser (nlsql) ──► plan + SQL
        │ no plan
        ▼
optional LLM proposal (JSON) ──► schema validation ──► SQL guard
        │
        ▼
Store.run_query (DuckDB, read-only, row cap, timeout)
        │
        ▼
result shape (table/kpi/bar/line) ──► narrator facts ──► answer
```

The deterministic path always runs first. A model is an optional fallback and
can never fabricate a number: the narrator receives a `facts` dictionary built
from the returned rows, and model prose is discarded when it mentions a number
that is not in that dictionary.

`POST /api/datasets/{id}/ask/stream` emits the same frames as the non-streaming
endpoint over Server-Sent Events: `stage`, `answer`, `error`, `done`.

## Storage

DuckDB is the only database. Each uploaded dataset becomes a table named
`ds_<slug>`. The registry table keeps display metadata:

```sql
_atlas_datasets(
  id, name, description, table_name, source, rows, cols, bytes,
  created_at, notes_json, profile_json, insights_json, tags_json, deleted_at, glossary_json
)
```
Schema changes are recorded in `_atlas_schema(version, applied_at, note)`.
Migrations are additive and idempotent:

| Version | Change |
| --- | --- |
| 1 | Base dataset registry. |
| 2 | `description` and `tags_json`. |
| 3 | `deleted_at` for the 30-day trash. |
| 4 | `glossary_json` for per-column business definitions. |

Deletion is a soft delete. A purge drops the table, removes the registry row, and
deletes the archived raw file. Startup purges rows whose `deleted_at` is older
than 30 days.

Uploads are validated by extension and magic bytes, streamed with a size cap,
archived atomically as `raw/<dataset-id>-<name>`, and registered only after the
table is created.

## Security boundaries

| Boundary | Control |
| --- | --- |
| Network exposure | Loopback by default. `ATLAS_AUTH_TOKEN` is required for non-loopback clients; `?token=` exchanges for an HttpOnly, SameSite cookie. |
| Browser requests | CSP with `script-src 'self'`, `frame-ancestors 'self'`, `object-src 'none'`; Origin and `Sec-Fetch-Site` checks on every mutation. |
| Uploads | Extension allowlist, magic-byte signatures, 128 MB limit, path-safe names, atomic archive. |
| SQL | One `SELECT`/`WITH` statement, comments stripped, DDL/DML/`ATTACH`/file and catalog functions rejected, row cap, watchdog timeout, DuckDB external access disabled. |
| Prompt injection | Model SQL is a JSON contract validated against the dataset schema, then passed through the same guard. A regression corpus covers injection attempts. |
| Report export | No scripts, no remote assets, optional PII redaction, formula neutralisation in CSV exports. |

See [`SECURITY.md`](../SECURITY.md) and [`threat-model.md`](threat-model.md) for
the full threat model.

## Frontend

- `landing.html` / `landing.css` / `landing.js`: editorial landing page with a
  canvas constellation, bundled fonts, and a live Ask demo.
- `index.html` / `styles.css` / `app.js`: the workspace. State is a small
  in-memory object; routing uses `#/d/<dataset>/<view>?q=...&f=column:value`.
- `charts.js`: dependency-free SVG renderers used by both surfaces.
- Event handling is delegated through `data-action` attributes. There is no
  framework and no inline script, so the CSP can stay strict.
- Saved questions and pinned insights live in `localStorage`
  (`atlas.saved.v1`, `atlas.pins.v1`); nothing is sent to a server.

## Testing

| Layer | Suite |
| --- | --- |
| Unit and API | `tests/test_*.py` (pytest), SQL guard, ingest, stats, NL parsing, Ask safety, security, platform. |
| Property-based | `tests/test_properties.py` (Hypothesis): CSV round-trips, quality bounds, numeric parsing, filter quoting, SQL guard contract. |
| Frontend unit | `tests/frontend/charts.test.mjs` (Node test runner): escaping, formatting, chart edge cases. |
| Browser / accessibility / print | `tests/e2e` (Playwright + axe-core + pypdf), enabled with `ATLAS_E2E=1`. |
| Benchmark | `benchmarks/run.py`: deterministic NL→SQL cases across the demo datasets. |
| CI | Python 3.11–3.14, coverage floor, cross-platform core tests, Docker smoke, Playwright/axe/PDF, dependency audit. |

## Deployment

Local:

```bash
pip install -e ".[excel,parquet]"
atlas --data-dir ./my-data --port 8050
```

Container:

```bash
docker build -t atlas .
docker run --rm -p 8080:8080 -v atlas-data:/data atlas
```

Backups are plain zip archives:

```bash
atlas backup --data-dir ./my-data --out atlas-backup.zip
atlas restore --data-dir ./my-data --from atlas-backup.zip
```

The Docker image runs as a non-root user, stores state in `/data`, and exposes a
health check against `/api/health`.

## Extension points

- **New reader**: add an extension to `SUPPORTED_EXTENSIONS` and a branch in
  `read_upload` / `inspect_upload`; add a signature check.
- **New chart type**: add a renderer in `charts.js` and wire it in `render`.
- **New report section**: add a key to the template maps in `report.py`, render
  it inside the `wanted` guard, and add a fixture assertion.
- **New analytics view**: add a core module returning plain JSON, a route, a tab
  in `app.js`, and an API test.
- **New LLM provider**: use the OpenAI-compatible path or extend `llm.py`; keep
  the JSON contract and schema validation unchanged.
