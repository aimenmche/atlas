# Atlas threat model

This is a short working threat model for a local-first application. It is
reviewed when a security-sensitive surface changes, not on a fixed calendar.

## Assets

| Asset | Why it matters |
| --- | --- |
| Uploaded datasets and DuckDB file | May contain personal, financial, or health data |
| Raw upload archive | Original file, including columns dropped during cleaning |
| Settings file | May contain a model API key |
| SQL execution path | A bypass could read files or mutate the workspace |
| Report HTML | Intended to leave the machine; must not contain injected script |
| Local service port | Any local process or webpage can attempt requests |

## Trust boundaries

1. **Browser to local API.** The UI is served from the same origin, but a
   malicious page in the same browser can still attempt cross-site requests.
2. **Upload bytes to parser.** Content is untrusted even when the extension
   looks familiar.
3. **Generated SQL to DuckDB.** Deterministic and model-proposed SQL are both
   untrusted until validated.
4. **Dataset values to HTML/SVG.** Cell text, column names, and category labels
   are untrusted output.
5. **Atlas to optional model endpoint.** Prompts may contain schema names and
   sampled values; the endpoint is outside the local trust boundary.
6. **Local data directory.** Assumed to be readable only by the user; Atlas does
   not add encryption at rest.

## STRIDE summary

| Threat | Example | Mitigation |
| --- | --- | --- |
| Spoofing | A malicious site posts to the local API | Origin and `Sec-Fetch-Site` checks on mutations |
| Tampering | SQL attempts `DROP`, `COPY`, or `ATTACH` | One-statement read-only guard, keyword/function blocklist, DuckDB external access off |
| Repudiation | A report has no provenance | SQL, row counts, timings, caveats, and dataset fingerprint in the evidence appendix |
| Information disclosure | PII appears in a shared report | PII detection and redaction controls; local-only default |
| Denial of service | A query or upload consumes the machine | Query watchdog, row caps, upload size cap, bounded JSON expansion |
| Elevation of privilege | A model proposes hidden tables or file reads | Schema validation, same SQL guard, no model access to the filesystem |
| Injection | Cell values or headers contain markup or prompt text | HTML escaping, inert report output, schema-constrained model contract |

## Implemented controls

- DuckDB opens with `enable_external_access=false`.
- The SQL guard allows one `SELECT`/`WITH`, strips comments, masks literals, and
  rejects DDL, DML, `ATTACH`, `COPY`, `PRAGMA`, file readers, and extension
  loading.
- Queries are row-capped and run under a watchdog timeout.
- Uploads are size-capped, extension-allowlisted, and signature-checked before
  parsing. Raw archives are written atomically.
- Mutating browser requests are checked against `Origin` and `Sec-Fetch-Site`.
- Responses set CSP, `nosniff`, `SAMEORIGIN` framing, a strict referrer policy,
  and a restrictive permissions policy.
- Reports are self-contained HTML with no scripts or remote assets.
- API keys are masked in settings responses and never written to logs.
- Dependencies and GitHub Actions are monitored by Dependabot; `pip-audit` runs
  in CI in report-only mode until the first triage is complete.

## Residual risks

- **No authentication by default.** Loopback is assumed trusted. Binding to a
  LAN or public interface requires a reverse proxy with auth and TLS.
- **No encryption at rest.** Full-disk encryption is the user's responsibility.
- **Optional model calls leave the machine.** The user chooses the endpoint and
  should review its data policy. Prompt budgets and redaction are planned.
- **Local malware.** A process that can read the data directory can read the
  database; Atlas does not defend against a compromised host.
- **Report sharing.** A report is only as safe as the redaction choices made
  before export.

## Verification

The controls above are covered by `tests/test_security.py`,
`tests/test_guard_and_ingest.py`, and the API suite. New security-sensitive
routes should add a test that demonstrates the rejection path, not only the
happy path.
