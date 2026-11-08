"""Store migrations and metadata tests."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from atlas.core.store import Store


def _legacy_database(path: Path) -> None:
    con = duckdb.connect(str(path))
    con.execute(
        """
        CREATE TABLE _atlas_datasets (
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
    con.execute(
        "INSERT INTO _atlas_datasets VALUES "
        "('legacy', 'Legacy', 'ds_legacy', 'csv', 1, 1, 8, 'now', '[]', '{}', '[]')"
    )
    con.close()


def test_legacy_database_migrates_without_data_loss(tmp_path):
    path = tmp_path / "atlas.duckdb"
    _legacy_database(path)

    store = Store(path)
    try:
        version = store.execute("SELECT MAX(version) FROM _atlas_schema")[0][0]
        assert version == 4
        dataset = store.get_dataset("legacy")
        assert dataset["name"] == "Legacy"
        assert dataset["description"] == ""
        assert dataset["tags"] == []
        assert dataset["glossary"] == {}
    finally:
        store.close()


def test_metadata_roundtrip_and_tag_cleanup(tmp_path):
    store = Store(tmp_path / "atlas.duckdb")
    try:
        frame = pd.DataFrame({"value": [1, 2, 3]})
        store.save_dataset(
            "meta",
            "Meta",
            frame,
            {"rows": 3, "cols": 1, "memory_bytes": 24},
            [],
            "csv",
            [],
            description="Quarterly revenue",
            tags=["Finance", "finance", " monthly ", ""],
        )
        dataset = store.get_dataset("meta")
        assert dataset["description"] == "Quarterly revenue"
        assert dataset["tags"] == ["Finance", "monthly"]

        updated = store.update_dataset(
            "meta",
            name="Renamed",
            description="Updated",
            tags=["board"],
            glossary={"value": "  Net recognised revenue  ", "missing": " ", "": "ignored"},
        )
        assert updated["name"] == "Renamed"
        assert updated["description"] == "Updated"
        assert updated["tags"] == ["board"]
        assert updated["glossary"] == {"value": "Net recognised revenue"}
        assert store.list_datasets()[0]["tags"] == ["board"]
    finally:
        store.close()
