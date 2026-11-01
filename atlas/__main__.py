"""Console entry point: ``atlas`` (or ``python -m atlas``)."""
from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="atlas",
        description="Atlas - a local-first autonomous data analyst.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8050, help="Port (default: 8050).")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Directory for the DuckDB file and uploads (default: ./data).",
    )
    parser.add_argument("--reload", action="store_true", help="Reload on code changes (development).")
    args = parser.parse_args()

    # config.py reads this at import time, so set it before importing the app.
    if args.data_dir:
        os.environ["ATLAS_DATA_DIR"] = os.path.abspath(args.data_dir)

    import uvicorn

    uvicorn.run(
        "atlas.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
