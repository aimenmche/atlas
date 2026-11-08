# Contributing to Atlas

Thanks for taking a look. Atlas is a small, local-first project: one Python
service, one DuckDB file, and a zero-build browser interface.

## Prerequisites

- Python 3.11 or newer
- Node.js (for the JavaScript syntax checks and frontend tests)
- Optional: `openpyxl` for Excel, `pyarrow` for Parquet
- Optional: Playwright Chromium for the end-to-end tests

## Set up

```bash
git clone https://github.com/dzdzdzdzdzdz213/atlas
cd atlas
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -e ".[dev,excel]"
npm install
python -m playwright install chromium   # only for e2e
```

Run the app:

```bash
atlas --data-dir ./my-data --port 8050
```

Open <http://127.0.0.1:8050> for the landing page and
<http://127.0.0.1:8050/app> for the workspace.

## Before opening a pull request

```bash
python -m pytest --cov=atlas --cov-report=term-missing
python benchmarks/run.py
npm test
node --check atlas/static/app.js
node --check atlas/static/charts.js
node --check atlas/static/landing.js
node --check atlas/static/boot.js
python scripts/export_openapi.py
```

Browser tests are opt-in so the default suite stays fast and headless-free:

```bash
# PowerShell
$env:ATLAS_E2E="1"; python -m pytest tests/e2e
# bash
ATLAS_E2E=1 python -m pytest tests/e2e
```

The coverage floor is 70% for `atlas/`. Add a test for every behavior change,
including the rejection path for security-sensitive code. Accessibility target
is no `critical` or `serious` axe violations for WCAG 2.0/2.1 A/AA.

## Docs to update

- New or changed endpoint: `docs/api.md`, `docs/openapi.json`, and `docs/architecture.md`
- New dependency or runtime boundary: `SECURITY.md` and `docs/threat-model.md`
- User-visible change: `CHANGELOG.md` under the next version

## Versioning and releases

Versions are semantic and live in `pyproject.toml` and `atlas/__init__.py`.
Bump both with:

```bash
python scripts/bump_version.py patch     # or minor / major / --set X.Y.Z
```

Or run the **Bump version** workflow, which opens a pull request. Releases are
tag-driven: `release.yml` verifies the tag matches the package version, builds
the wheel and sdist, and publishes a GitHub release. Do not edit versions by
hand in only one file.

## Code style

- Python: 4-space indentation, type hints on public functions, `from __future__
  import annotations`, and a 100-character line target.
- JavaScript: plain ES2020 in an IIFE, no build step and no runtime dependency.
- CSS: reuse the design tokens in `atlas/static/styles.css` or
  `atlas/static/landing.css`; do not add a CDN or remote font.
- Reports: self-contained HTML only. No scripts, no remote assets, no external
  fonts.

## Issues and pull requests

1. Pick an issue from the Atlas Roadmap or open one with a clear reproduction.
2. Keep a pull request focused. Unrelated cleanups belong in a separate change.
3. Describe the user-visible behavior, the test you added, and any security or
   data-loss consideration.
4. Link the issue with `Closes #123`.
5. CI must be green on Python 3.11 through 3.14 before merge.

Security reports follow [`SECURITY.md`](SECURITY.md), not the public issue
tracker.

## Data and secrets

Never commit `data/`, `.env`, uploaded files, model keys, or generated
databases. The demo datasets in `datasets/` are synthetic and safe to commit.
