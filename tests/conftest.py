"""Shared test configuration.

Atlas reads its data directory at import time, so point it at a scratch folder
*before* any application module is imported. This keeps the demo database that
lives in ``atlas/data`` untouched while tests run.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

TEST_DATA_DIR = Path(tempfile.gettempdir()) / "atlas-pytest-data"
shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["ATLAS_DATA_DIR"] = str(TEST_DATA_DIR)

import pytest  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def saas_frame():
    from atlas.core.ingest import read_upload

    path = PROJECT_ROOT / "datasets" / "saas_revenue.csv"
    frame, _ = read_upload(path.name, path.read_bytes())
    return frame


@pytest.fixture(scope="session")
def saas_profile(saas_frame):
    from atlas.core.profile import build_profile

    return build_profile(saas_frame, "saas-revenue", "SaaS Revenue")
