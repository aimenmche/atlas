"""Console entry point: ``atlas`` (or ``python -m atlas``).

Commands:
  atlas                         start the local service
  atlas backup --out file.zip   snapshot the data directory
  atlas restore --from file.zip replace the data directory from a snapshot
  atlas watch --dir folder      upload new/changed files to a running service
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

WATCH_SUFFIXES = {".csv", ".tsv", ".txt", ".json", ".xlsx", ".xlsm", ".parquet", ".pq"}


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="atlas",
        description="Atlas - a local-first autonomous data analyst.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=["serve", "backup", "restore", "watch"],
        help="serve (default), backup, restore or watch a folder.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8050, help="Port (default: 8050).")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Directory for the DuckDB file and uploads (default: ./data).",
    )
    parser.add_argument("--reload", action="store_true", help="Reload on code changes (development).")
    parser.add_argument("--out", default=None, help="Backup archive path (backup).")
    parser.add_argument("--from", dest="source", default=None, help="Backup archive to restore.")
    parser.add_argument("--dir", dest="watch_dir", default=None, help="Folder to watch (watch).")
    parser.add_argument("--url", default="http://127.0.0.1:8050", help="Running Atlas URL (watch).")
    parser.add_argument("--interval", type=float, default=15.0, help="Watch interval seconds.")
    parser.add_argument("--once", action="store_true", help="Scan once and exit (watch).")
    parser.add_argument("--yes", action="store_true", help="Skip the restore confirmation.")
    args = parser.parse_args()

    if args.command == "backup":
        raise SystemExit(backup(args.data_dir, args.out))
    if args.command == "restore":
        raise SystemExit(restore(args.data_dir, args.source, assume_yes=args.yes))
    if args.command == "watch":
        raise SystemExit(watch(args.watch_dir, args.url, args.interval, once=args.once))

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


def _data_dir(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return Path(os.environ.get("ATLAS_DATA_DIR", Path.cwd() / "data")).expanduser().resolve()


def backup(data_dir: str | None, out: str | None) -> int:
    source = _data_dir(data_dir)
    if not source.exists():
        print(f"No data directory at {source}", file=sys.stderr)
        return 1
    destination = Path(out or f"atlas-backup-{time.strftime('%Y%m%d-%H%M%S')}.zip").resolve()
    manifest = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str(source),
        "files": [],
    }
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or path.name.endswith(".part") or ".pre-restore" in path.name:
                continue
            relative = path.relative_to(source).as_posix()
            archive.write(path, arcname=relative)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            manifest["files"].append({"path": relative, "bytes": path.stat().st_size, "sha256": digest})
        archive.writestr("atlas-backup.json", json.dumps(manifest, indent=2))
    print(f"Backup written to {destination} ({len(manifest['files'])} files)")
    print("Stop the Atlas server before taking a backup of a live DuckDB file.")
    return 0


def restore(data_dir: str | None, source: str | None, assume_yes: bool = False) -> int:
    if not source:
        print("Pass --from path/to/backup.zip", file=sys.stderr)
        return 1
    archive_path = Path(source).expanduser().resolve()
    if not archive_path.exists():
        print(f"No backup at {archive_path}", file=sys.stderr)
        return 1
    target = _data_dir(data_dir)
    if not assume_yes:
        answer = input(f"Replace {target} with {archive_path.name}? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Restore cancelled.")
            return 1
    with tempfile.TemporaryDirectory(prefix="atlas-restore-") as temp:
        staging = Path(temp) / "data"
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if "atlas.duckdb" not in names:
                print("That archive does not contain atlas.duckdb.", file=sys.stderr)
                return 1
            for name in names:
                destination = (staging / name).resolve()
                if staging.resolve() not in destination.parents and destination != staging.resolve():
                    print(f"Unsafe path in archive: {name}", file=sys.stderr)
                    return 1
            archive.extractall(staging)
        if target.exists():
            backup_dir = target.with_name(f"{target.name}.pre-restore-{time.strftime('%Y%m%d-%H%M%S')}")
            shutil.move(str(target), str(backup_dir))
            print(f"Previous data directory saved to {backup_dir}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging, target)
    print(f"Restored Atlas data into {target}")
    return 0


def watch(folder: str | None, url: str, interval: float, once: bool = False) -> int:
    if not folder:
        print("Pass --dir path/to/folder", file=sys.stderr)
        return 1
    import httpx

    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        print(f"Not a folder: {root}", file=sys.stderr)
        return 1
    state_path = root / ".atlas-watch.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}

    def scan() -> int:
        uploaded = 0
        for path in sorted(root.iterdir()):
            if not path.is_file() or path.name.startswith(".") or path.suffix.lower() not in WATCH_SUFFIXES:
                continue
            stat = path.stat()
            key = str(path)
            previous = state.get(key) or {}
            if previous.get("mtime") == stat.st_mtime and previous.get("size") == stat.st_size:
                continue
            try:
                with path.open("rb") as handle:
                    response = httpx.post(
                        f"{url.rstrip('/')}/api/datasets",
                        files={"file": (path.name, handle)},
                        data={"name": path.stem.replace("_", " ").replace("-", " ")},
                        timeout=300.0,
                    )
                response.raise_for_status()
                created = response.json()
                state[key] = {
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                    "dataset_id": created.get("id"),
                    "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                uploaded += 1
                print(f"Imported {path.name} -> {created.get('name')} ({created.get('rows', 0):,} rows)")
            except Exception as exc:  # keep watching after one bad file
                print(f"Could not import {path.name}: {exc}", file=sys.stderr)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return uploaded

    print(f"Watching {root} every {interval:g}s · {url}")
    while True:
        scan()
        if once:
            return 0
        time.sleep(max(1.0, interval))


if __name__ == "__main__":
    main()
