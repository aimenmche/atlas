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
                "CREATE TABLE IF NOT EXISTS _atlas_schema ("
                "version INTEGER NOT NULL, applied_at VARCHAR NOT NULL)"
            )
            current = self.con.execute(
                "SELECT COALESCE(MAX(version), 0) FROM _atlas_schema"
            ).fetchone()[0]
            if current == 0:
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
                self._record_version(1)
                current = 1
            if current < 2:
                columns = self._columns("_atlas_datasets")
                if "description" not in columns:
                    self.con.execute(
                        "ALTER TABLE _atlas_datasets ADD COLUMN description VARCHAR"
                    )
                if "tags_json" not in columns:
                    self.con.execute(
                        "ALTER TABLE _atlas_datasets ADD COLUMN tags_json VARCHAR"
                    )
                self._record_version(2)
                current = 2
            if current < 3:
                columns = self._columns("_atlas_datasets")
                if "deleted_at" not in columns:
                    self.con.execute(
                        "ALTER TABLE _atlas_datasets ADD COLUMN deleted_at VARCHAR"
                    )
                self._record_version(3)
                current = 3
            if current < 4:
                columns = self._columns("_atlas_datasets")
                if "glossary_json" not in columns:
                    self.con.execute(
                        "ALTER TABLE _atlas_datasets ADD COLUMN glossary_json VARCHAR"
                    )
                self._record_version(4)

    def _record_version(self, version: int) -> None:
        self.con.execute(
            "INSERT INTO _atlas_schema VALUES (?, ?)",
            [version, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())],
        )

    def _columns(self, table: str) -> set[str]:
        rows = self.con.execute(f"PRAGMA table_info('{table}')").fetchall()
        return {str(row[1]) for row in rows}

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
        description: str = "",
        tags: list[str] | None = None,
    ) -> dict:
        table = table_name(dataset_id)
        clean = frame_to_python(frame)
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tag_list = _clean_tags(tags)
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
                "INSERT INTO _atlas_datasets ("
                "id, name, description, table_name, source, rows, cols, bytes, "
                "created_at, notes_json, profile_json, insights_json, tags_json, glossary_json"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    dataset_id,
                    name,
                    description[:500],
                    table,
                    source,
                    int(profile["rows"]),
                    int(profile["cols"]),
                    int(profile["memory_bytes"]),
                    created_at,
                    json.dumps(notes, default=str),
                    json.dumps(profile, default=str),
                    json.dumps(insights, default=str),
                    json.dumps(tag_list, default=str),
                    json.dumps({}, default=str),
                ],
            )
        return {
            "id": dataset_id,
            "name": name,
            "description": description[:500],
            "tags": tag_list,
            "source": source,
            "rows": int(profile["rows"]),
            "cols": int(profile["cols"]),
            "bytes": int(profile["memory_bytes"]),
            "created_at": created_at,
        }

    def list_datasets(self, include_deleted: bool = False) -> list[dict]:
        where = "" if include_deleted else "WHERE deleted_at IS NULL "
        with self.lock:
            rows = self.con.execute(
                "SELECT id, name, description, source, rows, cols, bytes, created_at, tags_json, deleted_at "
                f"FROM _atlas_datasets {where}ORDER BY created_at DESC"
            ).fetchall()
        keys = [
            "id", "name", "description", "source", "rows", "cols", "bytes",
            "created_at", "tags_json", "deleted_at",
        ]
        items = []
        for row in rows:
            item = dict(zip(keys, row))
            item["tags"] = _loads(item.pop("tags_json"), [])
            items.append(item)
        return items

    def list_trash(self) -> list[dict]:
        return [item for item in self.list_datasets(include_deleted=True) if item.get("deleted_at")]

    def get_dataset(self, dataset_id: str) -> dict:
        with self.lock:
            row = self.con.execute(
                "SELECT id, name, description, table_name, source, rows, cols, bytes, "
                "created_at, notes_json, profile_json, insights_json, tags_json, deleted_at, "
                "glossary_json "
                "FROM _atlas_datasets WHERE id = ?",
                [dataset_id],
            ).fetchone()
        if not row:
            raise DatasetNotFound(dataset_id)
        keys = [
            "id", "name", "description", "table_name", "source", "rows", "cols",
            "bytes", "created_at",
        ]
        data = dict(zip(keys, row[:9]))
        data["description"] = data.get("description") or ""
        data["notes"] = _loads(row[9], [])
        data["profile"] = _loads(row[10], {})
        data["insights"] = _loads(row[11], [])
        data["tags"] = _loads(row[12], [])
        data["deleted_at"] = row[13]
        data["glossary"] = _loads(row[14], {})
        return data

    def update_dataset(
        self,
        dataset_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        glossary: dict[str, str] | None = None,
    ) -> dict:
        fields: list[str] = []
        params: list[Any] = []
        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if description is not None:
            fields.append("description = ?")
            params.append(description[:500])
        if tags is not None:
            fields.append("tags_json = ?")
            params.append(json.dumps(_clean_tags(tags), default=str))
        if glossary is not None:
            fields.append("glossary_json = ?")
            params.append(json.dumps(_clean_glossary(glossary), default=str))
        if fields:
            params.append(dataset_id)
            with self.lock:
                self.con.execute(
                    f"UPDATE _atlas_datasets SET {', '.join(fields)} WHERE id = ?",
                    params,
                )
        return self.get_dataset(dataset_id)

    def update_insights(self, dataset_id: str, insights: list[dict]) -> None:
        with self.lock:
            self.con.execute(
                "UPDATE _atlas_datasets SET insights_json = ? WHERE id = ?",
                [json.dumps(insights, default=str), dataset_id],
            )

    def delete_dataset(self, dataset_id: str) -> None:
        """Permanently remove a dataset and its table."""
        self.purge_dataset(dataset_id)

    def trash_dataset(self, dataset_id: str) -> dict:
        self.get_dataset(dataset_id)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self.lock:
            self.con.execute(
                "UPDATE _atlas_datasets SET deleted_at = ? WHERE id = ?",
                [stamp, dataset_id],
            )
        return self.get_dataset(dataset_id)

    def restore_dataset(self, dataset_id: str) -> dict:
        self.get_dataset(dataset_id)
        with self.lock:
            self.con.execute(
                "UPDATE _atlas_datasets SET deleted_at = NULL WHERE id = ?",
                [dataset_id],
            )
        return self.get_dataset(dataset_id)

    def purge_dataset(self, dataset_id: str) -> None:
        dataset = self.get_dataset(dataset_id)
        with self.lock:
            self.con.execute(f"DROP TABLE IF EXISTS {quote_ident(dataset['table_name'])}")
            self.con.execute("DELETE FROM _atlas_datasets WHERE id = ?", [dataset_id])

    def purge_expired_trash(self, days: int = 30) -> int:
        """Drop datasets that have sat in the trash for longer than ``days``."""
        cutoff = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - max(1, days) * 86400)
        )
        expired = [item["id"] for item in self.list_trash() if (item.get("deleted_at") or "") < cutoff]
        for dataset_id in expired:
            try:
                self.purge_dataset(dataset_id)
            except DatasetNotFound:
                continue
        return len(expired)

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

    def explain(self, dataset_id: str, sql: str, timeout: float = 3.0) -> None:
        """Plan a query against the real table without executing it.

        Raises the underlying DuckDB error when a column or table is missing,
        which lets the analyst feed a precise message back to the model.
        """
        validate_sql(sql)
        dataset = self.get_dataset(dataset_id)
        if "{" + "table}" in sql:
            sql = sql.replace("{table}", quote_ident(dataset["table_name"]))
        with self.lock:
            timer = threading.Timer(timeout, self._interrupt)
            timer.daemon = True
            timer.start()
            try:
                self.con.execute("EXPLAIN " + sql)
            finally:
                timer.cancel()

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


def _clean_tags(tags: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in tags or []:
        tag = str(raw).strip()[:32]
        key = tag.lower()
        if tag and key not in seen:
            seen.add(key)
            out.append(tag)
    return out[:12]


def _clean_glossary(glossary: dict[str, str] | None) -> dict[str, str]:
    """Keep non-empty definitions, bounded by column name and description length."""
    out: dict[str, str] = {}
    for raw_name, raw_definition in (glossary or {}).items():
        name = " ".join(str(raw_name).split())[:120]
        definition = " ".join(str(raw_definition).split())[:280]
        if name and definition:
            out[name] = definition
        if len(out) >= 200:
            break
    return out


def _references_table(sql: str, table: str) -> bool:
    return table.lower() in sql.lower()
