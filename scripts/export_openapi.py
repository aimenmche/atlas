"""Export the Atlas OpenAPI schema without starting a server.

    python scripts/export_openapi.py
    python scripts/export_openapi.py --out docs/openapi.json

The generated Swagger/ReDoc pages are intentionally disabled because they load
assets from a CDN. The schema itself is plain JSON and stays local.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "docs" / "openapi.json",
        help="Destination file (default: docs/openapi.json).",
    )
    args = parser.parse_args()

    # Importing the app reads ATLAS_DATA_DIR at import time. Point it at a
    # throwaway directory so exporting docs never touches real data.
    os.environ.setdefault(
        "ATLAS_DATA_DIR", str(Path(tempfile.gettempdir()) / "atlas-openapi-export")
    )
    sys.path.insert(0, str(ROOT))

    from atlas.app import app  # noqa: E402

    schema = app.openapi()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths = len(schema.get("paths") or {})
    print(f"Wrote {args.out} ({paths} paths, OpenAPI {schema.get('openapi')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
