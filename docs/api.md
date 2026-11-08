# HTTP API

Atlas serves one FastAPI application from `atlas/app.py`. The browser surfaces
use the same JSON API that scripts can call. Everything is same-origin and
local by default.

- Base URL: `http://127.0.0.1:8050` (or `--port`)
- Schema: `GET /openapi.json`
- Interactive docs are intentionally disabled because the generated Swagger and
  ReDoc pages fetch assets from a CDN. Use the schema above or this page.
- Export a copy with `python scripts/export_openapi.py` (writes
  `docs/openapi.json`).

## Conventions

| Topic | Behaviour |
| --- | --- |
| Content type | JSON unless noted. Reports return `text/html`; downloads set `Content-Disposition`. |
| Errors | `{"detail": "..."}` with `400` (bad input), `401` (auth), `404` (missing dataset), `413` (upload too large), or `422` (schema validation). |
| Request IDs | Send `X-Request-ID`; the same value is echoed. Otherwise Atlas generates a 32-character id. |
| Auth | Off on loopback. When `ATLAS_AUTH_TOKEN` is set, non-loopback requests need `Authorization: Bearer <token>` or `X-Atlas-Token`. `GET /any/path?token=<token>` exchanges the token for an HttpOnly `atlas_token` cookie. |
| Mutations | `POST`, `PATCH`, and `DELETE` require a same-origin `Origin`/`Sec-Fetch-Site` context. |
| Filters | `[{"column": "region", "value": "EMEA"}]`, at most 8, applied as `column = value` inside a filtered subquery. |
| Limits | Uploads are capped at 128 MB. Queries return at most the configured row limit and are cancelled after the configured timeout. |

## Health and datasets

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Version, dataset count, row count, LLM mode, data directory. |
| `GET` | `/api/datasets` | List active datasets with quality summaries. |
| `POST` | `/api/datasets/inspect` | Multipart `file`: preview headers, sheets, JSON paths, detected header row. Does not ingest. |
| `POST` | `/api/datasets` | Multipart `file` plus optional `name`, `sheet`, `header_row`, `json_path`. Returns the new dataset and profile summary. |
| `GET` | `/api/datasets/{id}` | Full profile, insights, tags, description, and quality. |
| `PATCH` | `/api/datasets/{id}` | Update `name`, `description`, `tags` (max 12, 32 chars each), and `glossary` (column → definition, max 200 terms, 280 chars each). |
| `DELETE` | `/api/datasets/{id}` | Soft delete (30-day trash). `?permanent=true` purges immediately. |
| `GET` | `/api/trash` | List recoverable datasets. |
| `POST` | `/api/datasets/{id}/restore` | Restore from trash. |
| `DELETE` | `/api/trash/{id}` | Permanently delete a trashed dataset. |
| `GET` | `/api/datasets/{id}/preview` | Paginated rows: `limit`, `offset`. |

Example:

```bash
curl -F "file=@sales.csv" -F "name=Sales 2026" http://127.0.0.1:8050/api/datasets
```

## Ask and query

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/datasets/{id}/query` | Run guarded read-only SQL against one dataset. |
| `POST` | `/api/datasets/{id}/ask` | Ask a question. Optional `history` (max 6 turns) and `filters`. |
| `POST` | `/api/datasets/{id}/ask/stream` | Same payload over Server-Sent Events: `stage`, `answer`, `error`, `done`. |
| `POST` | `/api/datasets/{id}/insights/refresh` | Re-profile and rebuild ranked insights. |

```json
{
  "question": "How did revenue change last quarter?",
  "history": [{"role": "user", "content": "Focus on EMEA."}],
  "filters": [{"column": "region", "value": "EMEA"}]
}
```

`/query` accepts `{"sql": "SELECT ... FROM {table}", "limit": 500, "filters": [...]}`.
`{table}` is replaced with the dataset table. The SQL guard rejects anything
that is not a single `SELECT`/`WITH` statement, including DDL, `ATTACH`, file
functions, catalog reads, and comments.

A `422` from `/ask` can carry clarification choices:

```json
{
  "detail": {
    "message": "Which metric do you mean?",
    "choices": ["revenue", "seats"]
  }
}
```

## Analysis

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/datasets/{id}/compare` | Period-over-period comparison with waterfall and significance. |
| `POST` | `/api/datasets/{id}/cohorts` | Cohort retention matrix. |
| `POST` | `/api/datasets/{id}/relationships` | Correlation matrix or lag analysis. |
| `POST` | `/api/datasets/{id}/forecast` | Model comparison, rolling backtest, calibrated interval, calendar effects, exclusions. |
| `GET` | `/api/datasets/{id}/anomalies` | Robust-z anomaly scan with `sensitivity` (`low`, `medium`, `high`, `extreme`) and `exclude` dates. |

Forecast payload:

```json
{
  "date_col": "date",
  "value_col": "revenue",
  "horizon": 6,
  "freq": "auto",
  "agg": "sum",
  "calendar": true,
  "exclude": "2025-12-25,2026-01-01",
  "include_anomalies": true
}
```

The response includes `model`, `forecast`, `candidates`, `backtest`,
`interval`, `calendar`, `excluded_dates`, `anomalies`, `metrics`, and
`warnings`.

## Reports and settings

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/datasets/{id}/report` | Self-contained HTML report. |
| `GET` | `/api/settings` | Provider, model, timeout, limits, redaction. API keys are never returned. |
| `POST` | `/api/settings/test` | Validate the configured model endpoint. |

Report query parameters:

| Parameter | Meaning |
| --- | --- |
| `download` | `true` adds an attachment filename. |
| `title` | Report title (120 chars). |
| `brand` | Brand label (40 chars). |
| `sections` | Comma-separated: `read`, `evidence`, `quality`, `columns`, `method`, `appendix`, `forecast`. |
| `template` | `full`, `executive`, `quality`, or `forecast`. |
| `redact` | `true` masks PII columns and sampled values. |

The report contains no scripts, remote fonts, trackers, or external requests.
It prints to PDF cleanly from the browser.

## Static surfaces

| Path | Purpose |
| --- | --- |
| `/` | Landing page and live demo. |
| `/app` | Analyst workspace. `/app/` redirects with `307`. |
| `/static/*` | Bundled CSS, JavaScript, fonts, and images. |
| `/openapi.json` | Machine-readable API schema. |
