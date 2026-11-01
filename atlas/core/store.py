"""DuckDB-backed dataset store and query runner."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from .ingest import frame_to_python
from .sqlguard import limit_sql, validate_sql
from .util import jsonable, quote_ident, table_name


class QueryTimeout(RuntimeError):
    pass


class DatasetNotFound(KeyError):
    pass


class Store:
    """Single-connection DuckDB store with a re-entrant lock.

    DuckDB serializes writes on a connection anyway; the lock also lets the
    watchdog call ``interrupt()`` safely from another thread.
    """

    def __init__(self, db_path: str | Path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(db_path)
        self.lock = threading.RLock()
        self.con = duckdb.connect(
            self.path,
            config={
                "enable_external_access": "false",
                "threads": "4",
                "memory_limit": "2GB",
            },
        )
        self._init()

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #
    def _init(self) -> None:
        with self.lock:
            self.con.execute(
                """
                CREATE TABLE IF NOT EXISTS _atlas_datasets (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR,
                    table_name VARCHAR,
                    source VARCHAR,
                    rows BIGINT,
                    cols INTEGER,
                    bytes BIGINT,
                    created_at VARCHAR,
                    notes_json VARCHAR,
                    profile_json VARCHAR,
                    insights_json VARCHAR
                )
                """
            )

    # ------------------------------------------------------------------ #
    # Datasets
    # ------------------------------------------------------------------ #
    def save_dataset(
        self,
        dataset_id: str,
        name: str,
        frame: pd.DataFrame,
        profile: dict,
        insights: list[dict],
        source: str,
        notes: list[str],
    ) -> dict:
        table = table_name(dataset_id)
        clean = frame_to_python(frame)
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self.lock:
            self.con.register("_atlas_tmp_frame", clean)
            try:
                self.con.execute(
                    f"CREATE OR REPLACE TABLE {quote_ident(table)} AS "
                    "SELECT * FROM _atlas_tmp_frame"
                )
            finally:
                self.con.unregister("_atlas_tmp_frame")
            self.con.execute("DELETE FROM _atlas_datasets WHERE id = ?", [dataset_id])
            self.con.execute(
                "INSERT INTO _atlas_datasets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    dataset_id,
                    name,
                    table,
                    source,
                    int(profile["rows"]),
                    int(profile["cols"]),
                    int(profile["memory_bytes"]),
                    created_at,
                    json.dumps(notes, default=str),
                    json.dumps(profile, default=str),
                    json.dumps(insights, default=str),
                ],
            )
        return {
            "id": dataset_id,
            "name": name,
            "source": source,
            "rows": int(profile["rows"]),
            "cols": int(profile["cols"]),
            "bytes": int(profile["memory_bytes"]),
            "created_at": created_at,
        }

    def list_datasets(self) -> list[dict]:
        with self.lock:
            rows = self.con.execute(
                "SELECT id, name, source, rows, cols, bytes, created_at "
                "FROM _atlas_datasets ORDER BY created_at DESC"
            ).fetchall()
        keys = ["id", "name", "source", "rows", "cols", "bytes", "created_at"]
        return [dict(zip(keys, row)) for row in rows]

    def get_dataset(self, dataset_id: str) -> dict:
        with self.lock:
            row = self.con.execute(
                "SELECT id, name, table_name, source, rows, cols, bytes, created_at, "
                "notes_json, profile_json, insights_json FROM _atlas_datasets WHERE id = ?",
                [dataset_id],
            ).fetchone()
        if not row:
            raise DatasetNotFound(dataset_id)
        keys = ["id", "name", "table_name", "source", "rows", "cols", "bytes", "created_at"]
        data = dict(zip(keys, row[:8]))
        data["notes"] = _loads(row[8], [])
        data["profile"] = _loads(row[9], {})
        data["insights"] = _loads(row[10], [])
        return data

    def update_insights(self, dataset_id: str, insights: list[dict]) -> None:
        with self.lock:
            self.con.execute(
                "UPDATE _atlas_datasets SET insights_json = ? WHERE id = ?",
                [json.dumps(insights, default=str), dataset_id],
            )

    def delete_dataset(self, dataset_id: str) -> None:
        dataset = self.get_dataset(dataset_id)
        with self.lock:
            self.con.execute(f"DROP TABLE IF EXISTS {quote_ident(dataset['table_name'])}")
            self.con.execute("DELETE FROM _atlas_datasets WHERE id = ?", [dataset_id])

    def load_frame(self, dataset_id: str, limit: int | None = None) -> pd.DataFrame:
        dataset = self.get_dataset(dataset_id)
        sql = f"SELECT * FROM {quote_ident(dataset['table_name'])}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self.lock:
            return self.con.execute(sql).df()

    def table(self, dataset_id: str) -> str:
        return self.get_dataset(dataset_id)["table_name"]

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    def run_query(
        self,
        dataset_id: str,
        sql: str,
        params: list | None = None,
        timeout: float = 8.0,
        limit: int = 1000,
    ) -> dict:
        validate_sql(sql)
        dataset = self.get_dataset(dataset_id)
        if dataset["table_name"].lower() not in sql.lower() and not _references_table(sql, dataset["table_name"]):
            sql = sql.replace("{table}", quote_ident(dataset["table_name"]))
        safe_sql = limit_sql(sql, limit)
        started = time.perf_counter()
        with self.lock:
            timer = threading.Timer(timeout, self._interrupt)
            timer.daemon = True
            timer.start()
            try:
                cursor = self.con.execute(safe_sql, params or [])
                columns = [d[0] for d in (cursor.description or [])]
                rows = cursor.fetchmany(limit + 1) if columns else []
            except duckdb.InterruptException as exc:
                raise QueryTimeout(f"Query exceeded {timeout:.0f}s and was cancelled.") from exc
            except Exception as exc:
                if "interrupt" in str(exc).lower():
                    raise QueryTimeout(f"Query exceeded {timeout:.0f}s and was cancelled.") from exc
                raise
            finally:
                timer.cancel()
        truncated = len(rows) > limit
        rows = rows[:limit]
        elapsed = (time.perf_counter() - started) * 1000
        return {
            "columns": columns,
            "rows": [[jsonable(v) for v in row] for row in rows],
            "row_count": len(rows),
            "truncated": truncated,
            "elapsed_ms": round(elapsed, 1),
            "sql": sql,
        }

    def _interrupt(self) -> None:
        try:
            self.con.interrupt()
        except Exception:
            pass

    def execute(self, sql: str, params: list | None = None):
        with self.lock:
            return self.con.execute(sql, params or []).fetchall()

    def close(self) -> None:
        try:
            self.con.close()
        except Exception:
            pass


def _loads(raw: Any, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _references_table(sql: str, table: str) -> bool:
    return table.lower() in sql.lower()
