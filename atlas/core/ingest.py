"""File ingestion: bytes in, a clean and typed DataFrame out.

Handles encoding drift, delimiter sniffing, messy headers, business-formatted
numbers ($1,234.50 / (12.4) / 7.2%) and date-string inference. Every mutation is
recorded in ``meta['notes']`` so the UI can tell the user what happened.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
from typing import Any

import numpy as np
import pandas as pd

from .semantics import parse_number
from .util import pretty

MAX_ROWS = 300_000
DATE_HINTS = {"date", "day", "week", "month", "quarter", "year", "timestamp", "time", "period"}
ID_HINTS = {"id", "key", "code", "sku", "uuid", "guid", "ref"}


class IngestError(ValueError):
    """Raised when a file cannot be interpreted as tabular data."""


def read_upload(filename: str, data: bytes) -> tuple[pd.DataFrame, dict]:
    if not data:
        raise IngestError("The file is empty.")
    name = (filename or "upload").strip()
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "csv"
    notes: list[str] = []
    meta: dict[str, Any] = {"filename": name, "format": ext, "bytes": len(data)}

    if ext in {"xlsx", "xlsm", "xls"}:
        df = _read_excel(data, ext)
        meta["format"] = "excel"
    elif ext == "json":
        df = _read_json(data)
        meta["format"] = "json"
    elif ext in {"parquet", "pq"}:
        df = _read_parquet(data)
        meta["format"] = "parquet"
    elif ext in {"tsv", "tab"}:
        df, encoding = _read_csv(data, delimiter="\t")
        meta.update({"format": "tsv", "encoding": encoding})
    else:
        df, encoding, delimiter = _read_csv(data)
        meta.update({"format": "csv", "encoding": encoding, "delimiter": delimiter})

    if df.empty and len(df.columns) == 0:
        raise IngestError("No tabular data found in the file.")

    meta["raw_rows"] = int(len(df))
    df, clean_notes = clean_frame(df)
    notes.extend(clean_notes)
    if len(df) > MAX_ROWS:
        df = df.head(MAX_ROWS)
        notes.append(f"Large file: analysis limited to the first {MAX_ROWS:,} rows.")
        meta["truncated"] = True
    meta["rows"] = int(len(df))
    meta["cols"] = int(len(df.columns))
    meta["notes"] = notes
    return df, meta


# --------------------------------------------------------------------------- #
# Readers
# --------------------------------------------------------------------------- #
def _decode(data: bytes) -> tuple[str, str]:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def _sniff(text: str) -> str:
    sample = text[:10_000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in (",", ";", "\t", "|")}
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else ","


def _read_csv(data: bytes, delimiter: str | None = None) -> tuple[pd.DataFrame, str, str]:
    text, encoding = _decode(data)
    if not text.strip():
        raise IngestError("The file contains no text.")
    delim = delimiter or _sniff(text)
    try:
        df = pd.read_csv(
            io.StringIO(text),
            sep=delim,
            engine="c",
            skip_blank_lines=True,
            low_memory=False,
            nrows=MAX_ROWS + 1,
        )
    except (pd.errors.ParserError, ValueError):
        try:
            df = pd.read_csv(
                io.StringIO(text), sep=None, engine="python", skip_blank_lines=True,
                nrows=MAX_ROWS + 1,
            )
            delim = "auto"
        except Exception as exc:  # pragma: no cover - defensive
            raise IngestError(f"Could not parse the CSV file: {exc}") from exc
    if df.shape[1] <= 1 and delim != "auto":
        for candidate in (",", ";", "\t", "|"):
            if candidate != delim and text.count(candidate) > text.count("\n"):
                try:
                    alt = pd.read_csv(io.StringIO(text), sep=candidate, nrows=MAX_ROWS + 1)
                    if alt.shape[1] > df.shape[1]:
                        df, delim = alt, candidate
                        break
                except Exception:
                    continue
    return df, encoding, delim


def _read_json(data: bytes) -> pd.DataFrame:
    text, _ = _decode(data)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IngestError(f"Invalid JSON: {exc.msg} at line {exc.lineno}.") from exc
    if isinstance(payload, dict):
        for key in ("data", "rows", "records", "results", "items"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list) or not payload:
        raise IngestError("JSON must be an array of records or an object of arrays.")
    if all(isinstance(item, dict) for item in payload):
        return pd.json_normalize(payload)
    if all(isinstance(item, list) for item in payload):
        width = max(len(r) for r in payload)
        return pd.DataFrame(payload, columns=[f"column_{i + 1}" for i in range(width)])
    return pd.DataFrame({"value": payload})


def _read_excel(data: bytes, ext: str) -> pd.DataFrame:
    try:
        import openpyxl  # noqa: F401
    except ImportError as exc:
        raise IngestError(
            "Excel support needs openpyxl. Install it with: pip install openpyxl"
        ) from exc
    try:
        return pd.read_excel(io.BytesIO(data))
    except Exception as exc:
        raise IngestError(f"Could not read the workbook: {exc}") from exc


def _read_parquet(data: bytes) -> pd.DataFrame:
    try:
        return pd.read_parquet(io.BytesIO(data))
    except ImportError:
        pass
    except Exception as exc:
        raise IngestError(f"Could not read the Parquet file: {exc}") from exc
    try:  # DuckDB can read parquet without pyarrow
        import duckdb
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as fh:
            fh.write(data)
            path = Path(fh.name)
        con = duckdb.connect(":memory:")
        try:
            return con.execute(f"SELECT * FROM read_parquet('{path.as_posix()}')").df()
        finally:
            con.close()
            path.unlink(missing_ok=True)
    except Exception as exc:
        raise IngestError("Parquet support needs pyarrow: pip install pyarrow") from exc


# --------------------------------------------------------------------------- #
# Cleaning & type inference
# --------------------------------------------------------------------------- #
def clean_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    notes: list[str] = []
    df = df.copy()

    # pandas artifact columns from trailing delimiters
    drop = [c for c in df.columns if str(c).startswith("Unnamed:") and df[c].isna().all()]
    if drop:
        df = df.drop(columns=drop)

    df.columns = _clean_headers(df.columns)
    df = df.dropna(how="all")
    if len(df) == 0:
        raise IngestError("Every row is empty after cleaning.")

    # Normalize strings
    for col in df.columns:
        if _is_stringy(df[col]):
            s = df[col].astype("object")
            s = s.map(lambda v: v.strip() if isinstance(v, str) else v)
            s = s.map(lambda v: None if isinstance(v, str) and not v else v)
            df[col] = s

    converted: list[str] = []
    for col in df.columns:
        s = df[col]
        if not _is_stringy(s):
            if pd.api.types.is_numeric_dtype(s):
                df[col] = s.replace([np.inf, -np.inf], np.nan)
            continue

        bools = _try_boolean(s)
        if bools is not None:
            df[col] = bools
            converted.append(f"{pretty(str(col))} -> boolean")
            continue

        numeric = _try_numeric(s, str(col))
        if numeric is not None:
            df[col] = numeric
            if _name_is_date(str(col)):
                pass
            converted.append(f"{pretty(str(col))} -> number")
            continue

        dates = _try_datetime(s, str(col))
        if dates is not None:
            df[col] = dates
            converted.append(f"{pretty(str(col))} -> date")
            continue

        df[col] = s.astype("object").where(pd.notna(s), None)

    if converted:
        notes.append("Inferred types: " + "; ".join(converted[:8]) + ("..." if len(converted) > 8 else ""))
    return df, notes


def _clean_headers(columns: Any) -> list[str]:
    out: list[str] = []
    seen: dict[str, int] = {}
    for i, raw in enumerate(columns):
        name = str(raw).replace("\ufeff", "").strip()
        name = re.sub(r"\s+", " ", name)
        if not name:
            name = f"column_{i + 1}"
        key = name.lower()
        if key in seen:
            seen[key] += 1
            name = f"{name} ({seen[key]})"
        else:
            seen[key] = 1
        out.append(name[:120])
    return out


def _is_stringy(s: pd.Series) -> bool:
    dtype = s.dtype
    return isinstance(dtype, pd.StringDtype) or pd.api.types.is_object_dtype(dtype) or str(dtype) in {"str", "string"}


def _name_is_date(name: str) -> bool:
    tokens = set(re.split(r"[^a-z0-9]+", name.lower()))
    tokens.discard("")
    return bool(tokens & DATE_HINTS)


def _name_is_id(name: str) -> bool:
    tokens = set(re.split(r"[^a-z0-9]+", name.lower()))
    tokens.discard("")
    return bool(tokens & ID_HINTS)


def _try_boolean(s: pd.Series) -> pd.Series | None:
    values = s.dropna().astype(str).str.strip().str.lower().unique()
    if len(values) == 0 or len(values) > 2:
        return None
    universe = {"true", "false", "t", "f", "yes", "no", "y", "n", "1", "0"}
    if not set(values) <= universe:
        return None
    positives = {"true", "t", "yes", "y", "1"}
    mapping = {v: v in positives for v in values}
    return s.map(lambda v: None if pd.isna(v) else mapping.get(str(v).strip().lower()))


def _try_numeric(s: pd.Series, name: str) -> pd.Series | None:
    if _name_is_id(name):
        return None
    non_null = s.dropna()
    if non_null.empty:
        return None
    strings = non_null.astype(str)
    # preserve leading-zero codes such as "007"
    leading_zero = strings.str.match(r"^0\d+$").mean()
    if leading_zero > 0.5:
        return None
    # long digit strings are likely identifiers, not quantities
    long_digits = strings.str.fullmatch(r"\d{15,}").mean()
    if long_digits > 0.3:
        return None
    parsed = s.map(parse_number)
    ratio = parsed.notna().sum() / max(1, non_null.size)
    if ratio < 0.95:
        return None
    # If the few failures are meaningful text, keep the column as text.
    failures = s.notna() & parsed.isna()
    if failures.sum() > non_null.size * 0.05:
        return None
    return parsed.astype("float64")


def _try_datetime(s: pd.Series, name: str) -> pd.Series | None:
    non_null = s.dropna()
    if non_null.empty:
        return None
    strings = non_null.astype(str)
    hinted = _name_is_date(name)
    # Avoid turning bare identifiers or small integers into dates.
    looks_temporal = strings.str.contains(r"[-/:T ]", regex=True).mean() > 0.8
    if not hinted and not looks_temporal:
        return None
    try:
        parsed = pd.to_datetime(s, errors="coerce", format="mixed")
    except (ValueError, TypeError):
        return None
    ratio = parsed.notna().sum() / max(1, non_null.size)
    if ratio < (0.85 if hinted else 0.95):
        return None
    return parsed


def frame_to_python(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure dtypes DuckDB's pandas scanner accepts everywhere."""
    out = df.copy()
    for col in out.columns:
        s = out[col]
        if _is_stringy(s):
            out[col] = s.astype("object").where(pd.notna(s), None)
        elif pd.api.types.is_datetime64_any_dtype(s):
            out[col] = pd.to_datetime(s, errors="coerce")
        elif pd.api.types.is_bool_dtype(s):
            out[col] = s.astype("boolean").where(pd.notna(s), None)
        elif pd.api.types.is_numeric_dtype(s):
            out[col] = pd.to_numeric(s, errors="coerce").astype("float64")
    return out


def safe_value(value: Any) -> Any:
    """Convert a scalar to a Python value suitable for DuckDB insertion."""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value

