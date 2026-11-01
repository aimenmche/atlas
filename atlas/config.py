"""Runtime configuration.

Settings resolve from environment variables, then ``data/settings.json``
(written by the in-app settings panel), then defaults.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("ATLAS_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "atlas.duckdb"
SETTINGS_PATH = DATA_DIR / "settings.json"

MAX_UPLOAD_BYTES = int(os.environ.get("ATLAS_MAX_UPLOAD_MB", "128")) * 1024 * 1024
MAX_ANALYSIS_ROWS = int(os.environ.get("ATLAS_MAX_ANALYSIS_ROWS", "300000"))


@dataclass
class Settings:
    provider: str = "none"          # none | openai | ollama
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    temperature: float = 0.2
    query_timeout: float = 8.0
    row_limit: int = 1000

    @property
    def llm_enabled(self) -> bool:
        return self.provider in {"openai", "ollama"} and bool(self.model)

    def public(self) -> dict:
        d = asdict(self)
        d["api_key"] = "***" if self.api_key else ""
        d["llm_enabled"] = self.llm_enabled
        return d


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def load_settings() -> Settings:
    s = Settings(
        provider=_env("ATLAS_LLM_PROVIDER", "none").lower(),
        model=_env("ATLAS_LLM_MODEL", ""),
        base_url=_env("ATLAS_LLM_BASE_URL", ""),
        api_key=_env("ATLAS_LLM_API_KEY", ""),
        temperature=float(_env("ATLAS_LLM_TEMPERATURE", "0.2") or 0.2),
        query_timeout=float(_env("ATLAS_QUERY_TIMEOUT", "8") or 8),
        row_limit=int(_env("ATLAS_ROW_LIMIT", "1000") or 1000),
    )
    if SETTINGS_PATH.exists():
        try:
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            saved = {}
        for key, value in saved.items():
            if hasattr(s, key) and value not in (None, ""):
                setattr(s, key, value)
    return s


def save_settings(settings: Settings) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
