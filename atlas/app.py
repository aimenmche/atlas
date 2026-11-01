"""FastAPI application.

Local-first: one process, one DuckDB file, zero cloud dependencies. Uploads are
profiled on ingest, insights are stored alongside the data, and every answer
travels through the same read-only query sandbox.
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import (
    DATA_DIR,
    DB_PATH,
    MAX_UPLOAD_BYTES,
    RAW_DIR,
    ROOT,
    ensure_dirs,
    load_settings,
    save_settings,
)
from .core.agent import Analyst, AskError
from .core.analysis import build_insights
from .core.anomaly import detect_anomalies
from .core.forecast import forecast
from .core.ingest import IngestError, read_upload
from .core.profile import build_profile
from .core.report import build_report
from .core.sqlguard import SqlRejected
from .core.store import DatasetNotFound, QueryTimeout, Store
from .core.util import jsonable, new_id, pretty, quote_ident, slugify

log = logging.getLogger("atlas")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

STATIC_DIR = Path(__file__).resolve().parent / "static"

store: Store | None = None


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(_: FastAPI):
    global store
    ensure_dirs()
    store = Store(DB_PATH)
    try:
        _seed_demo(store)
    except Exception as exc:  # demo seeding must never block startup
        log.warning("Could not seed demo datasets: %s", exc)
    log.info("Atlas %s ready · %s", __version__, DB_PATH)
    yield
    if store is not None:
        store.close()
        store = None


app = FastAPI(
    title="Atlas",
    version=__version__,
    description="A local-first AI data analyst.",
    lifespan=lifespan,
)


def get_store() -> Store:
    global store
    if store is None:
        ensure_dirs()
        store = Store(DB_PATH)
    return store


def get_dataset(dataset_id: str) -> dict:
    try:
        return get_store().get_dataset(dataset_id)
    except DatasetNotFound:
        raise HTTPException(status_code=404, detail="Dataset not found.")


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
def landing() -> FileResponse:
    return FileResponse(STATIC_DIR / "landing.html")


@app.get("/app", include_in_schema=False)
def app_shell() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/app/", include_in_schema=False)
def app_shell_slash() -> RedirectResponse:
    return RedirectResponse(url="/app", status_code=307)


@app.get("/favicon.svg", include_in_schema=False)
def favicon() -> FileResponse:
    icon = STATIC_DIR / "favicon.svg"
    if not icon.exists():
        raise HTTPException(status_code=404, detail="No favicon.")
    return FileResponse(icon, media_type="image/svg+xml")


# --------------------------------------------------------------------------- #
# Meta
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict:
    settings = load_settings()
    datasets = get_store().list_datasets()
    return {
        "ok": True,
        "version": __version__,
        "datasets": len(datasets),
        "rows": sum(d.get("rows") or 0 for d in datasets),
        "llm": {
            "enabled": settings.llm_enabled,
            "provider": settings.provider,
            "model": settings.model,
        },
        "data_dir": str(DATA_DIR),
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# --------------------------------------------------------------------------- #
# Datasets
# --------------------------------------------------------------------------- #
@app.get("/api/datasets")
def list_datasets() -> dict:
    items = []
    for row in get_store().list_datasets():
        try:
            dataset = get_store().get_dataset(row["id"])
        except DatasetNotFound:
            continue
        profile = dataset.get("profile") or {}
        quality = profile.get("quality") or {}
        items.append({
            **row,
            "quality": quality.get("score"),
            "grade": quality.get("grade"),
            "time": profile.get("time"),
            "insights": len(dataset.get("insights") or []),
            "measures": len(profile.get("measures") or []),
            "dimensions": len(profile.get("dimensions") or []),
            "notes": dataset.get("notes") or [],
        })
    return {"datasets": items, "count": len(items)}


class RenamePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@app.post("/api/datasets", status_code=201)
def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
) -> dict:
    filename = Path(file.filename or "upload.csv").name
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.",
        )
    try:
        frame, meta = read_upload(filename, data)
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read that file: {exc}")

    display = (name or "").strip() or pretty(Path(filename).stem.replace("_", " ").replace("-", " "))
    display = display[:120]
    existing = {d["id"] for d in get_store().list_datasets()}
    dataset_id = slugify(display)
    if dataset_id in existing:
        dataset_id = f"{dataset_id}-{new_id()[:5]}"

    profile = build_profile(frame, dataset_id, display)
    insights = build_insights(frame, profile)
    result = get_store().save_dataset(
        dataset_id,
        display,
        frame,
        profile,
        insights,
        meta.get("format") or "file",
        meta.get("notes") or [],
    )
    try:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix.lower()[:8]
        (RAW_DIR / f"{dataset_id}{suffix}").write_bytes(data)
    except OSError:
        log.warning("Could not archive the raw upload for %s", dataset_id)

    return {
        **result,
        "quality": (profile.get("quality") or {}).get("score"),
        "grade": (profile.get("quality") or {}).get("grade"),
        "insights": len(insights),
        "notes": meta.get("notes") or [],
        "time": profile.get("time"),
    }


@app.get("/api/datasets/{dataset_id}")
def dataset_detail(dataset_id: str) -> dict:
    dataset = get_dataset(dataset_id)
    dataset.pop("table_name", None)
    return {
        **dataset,
        "row_count": dataset.get("rows"),
        "column_count": dataset.get("cols"),
    }


@app.patch("/api/datasets/{dataset_id}")
def rename_dataset(dataset_id: str, payload: RenamePayload) -> dict:
    dataset = get_dataset(dataset_id)
    name = payload.name.strip()
    get_store().execute(
        "UPDATE _atlas_datasets SET name = ? WHERE id = ?",
        [name, dataset_id],
    )
    return {"id": dataset_id, "name": name, "previous": dataset.get("name")}


@app.delete("/api/datasets/{dataset_id}")
def delete_dataset(dataset_id: str) -> dict:
    get_dataset(dataset_id)
    get_store().delete_dataset(dataset_id)
    raw = RAW_DIR / dataset_id
    for candidate in RAW_DIR.glob(f"{dataset_id}.*"):
        try:
            candidate.unlink()
        except OSError:
            pass
    return {"ok": True, "id": dataset_id}


@app.get("/api/datasets/{dataset_id}/preview")
def preview_dataset(dataset_id: str, limit: int = 40, offset: int = 0) -> dict:
    dataset = get_dataset(dataset_id)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    sql = f"SELECT * FROM {quote_ident(dataset['table_name'])} LIMIT {limit} OFFSET {offset}"
    result = get_store().run_query(dataset_id, sql, timeout=8.0, limit=limit)
    return {
        **result,
        "offset": offset,
        "total": dataset.get("rows"),
        "columns": result["columns"],
        "rows": result["rows"],
    }


# --------------------------------------------------------------------------- #
# SQL & questions
# --------------------------------------------------------------------------- #
class QueryPayload(BaseModel):
    sql: str = Field(min_length=1, max_length=50_000)
    limit: int | None = None


@app.post("/api/datasets/{dataset_id}/query")
def run_sql(dataset_id: str, payload: QueryPayload) -> dict:
    get_dataset(dataset_id)
    settings = load_settings()
    limit = max(1, min(int(payload.limit or settings.row_limit), 5000))
    try:
        return get_store().run_query(
            dataset_id,
            payload.sql,
            timeout=float(settings.query_timeout),
            limit=limit,
        )
    except SqlRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except QueryTimeout as exc:
        raise HTTPException(status_code=408, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_sql_error(exc))


class AskPayload(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@app.post("/api/datasets/{dataset_id}/ask")
def ask(dataset_id: str, payload: AskPayload) -> dict:
    get_dataset(dataset_id)
    analyst = Analyst(get_store(), load_settings())
    try:
        return analyst.ask(dataset_id, payload.question)
    except AskError as exc:
        raise HTTPException(status_code=422, detail=exc.as_dict())


@app.post("/api/datasets/{dataset_id}/ask/stream")
def ask_stream(dataset_id: str, payload: AskPayload) -> StreamingResponse:
    get_dataset(dataset_id)
    analyst = Analyst(get_store(), load_settings())

    question = payload.question

    def frames():
        try:
            for frame in analyst.ask_stream(dataset_id, question):
                data = json.dumps(frame.get("data"), ensure_ascii=False, default=str)
                yield f"event: {frame.get('event')}\ndata: {data}\n\n"
        except Exception as exc:  # the response has started; report in-band
            log.exception("Ask stream failed for %s", dataset_id)
            message = json.dumps({"error": "The analysis stream failed.", "detail": str(exc)})
            yield f"event: error\ndata: {message}\n\n"

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# --------------------------------------------------------------------------- #
# Analysis modules
# --------------------------------------------------------------------------- #
class ForecastPayload(BaseModel):
    date_col: str
    value_col: str
    horizon: int = 6
    freq: str | None = None
    agg: str = "sum"


@app.post("/api/datasets/{dataset_id}/forecast")
def run_forecast(dataset_id: str, payload: ForecastPayload) -> dict:
    dataset = get_dataset(dataset_id)
    _require_columns(dataset, payload.date_col, payload.value_col)
    frame = get_store().load_frame(dataset_id)
    try:
        result = forecast(
            frame,
            payload.date_col,
            payload.value_col,
            horizon=payload.horizon,
            freq=payload.freq,
            agg=payload.agg,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return jsonable({
        **result,
        "value_format": _column(dataset, payload.value_col).get("semantic"),
    })


@app.get("/api/datasets/{dataset_id}/anomalies")
def run_anomalies(
    dataset_id: str,
    date_col: str,
    value_col: str,
    agg: str = "sum",
    threshold: float = 3.5,
) -> dict:
    dataset = get_dataset(dataset_id)
    _require_columns(dataset, date_col, value_col)
    frame = get_store().load_frame(dataset_id)
    try:
        result = detect_anomalies(frame, date_col, value_col, agg=agg, threshold=threshold)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return jsonable({
        **result,
        "value_format": _column(dataset, value_col).get("semantic"),
    })


@app.post("/api/datasets/{dataset_id}/insights/refresh")
def refresh_insights(dataset_id: str) -> dict:
    dataset = get_dataset(dataset_id)
    frame = get_store().load_frame(dataset_id)
    profile = dataset.get("profile") or {}
    insights = build_insights(frame, profile)
    get_store().update_insights(dataset_id, insights)
    return {"insights": insights, "count": len(insights), "profile": profile}


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
@app.get("/api/datasets/{dataset_id}/report")
def download_report(dataset_id: str, download: bool = False):
    dataset = get_dataset(dataset_id)
    html = build_report(dataset)
    headers = {}
    if download:
        filename = f"atlas-{slugify(dataset.get('name') or 'report')}.html"
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return HTMLResponse(content=html, headers=headers)


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
class SettingsPayload(BaseModel):
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    temperature: float | None = None
    query_timeout: float | None = None
    row_limit: int | None = None


@app.get("/api/settings")
def read_settings() -> dict:
    return load_settings().public()


@app.put("/api/settings")
def write_settings(payload: SettingsPayload) -> dict:
    current = load_settings()
    values = payload.model_dump(exclude_unset=True)
    if "provider" in values and values["provider"] is not None:
        provider = str(values["provider"]).lower()
        if provider not in {"none", "openai", "ollama"}:
            raise HTTPException(status_code=400, detail="Provider must be none, openai or ollama.")
        current.provider = provider
    if "model" in values and values["model"] is not None:
        current.model = str(values["model"]).strip()[:120]
    if "base_url" in values and values["base_url"] is not None:
        current.base_url = str(values["base_url"]).strip()[:300]
    if "api_key" in values and values["api_key"] is not None:
        key = str(values["api_key"]).strip()
        if key != "***":
            current.api_key = key[:400]
    if "temperature" in values and values["temperature"] is not None:
        current.temperature = max(0.0, min(1.5, float(values["temperature"])))
    if "query_timeout" in values and values["query_timeout"] is not None:
        current.query_timeout = max(1.0, min(60.0, float(values["query_timeout"])))
    if "row_limit" in values and values["row_limit"] is not None:
        current.row_limit = max(10, min(10_000, int(values["row_limit"])))
    if current.provider == "none":
        current.model = ""
    save_settings(current)
    return current.public()


@app.post("/api/settings/test")
def test_settings() -> dict:
    from .core.llm import LLMClient

    settings = load_settings()
    if not settings.llm_enabled:
        raise HTTPException(status_code=400, detail="Configure a provider and model first.")
    client = LLMClient(settings)
    reply = client.complete(
        "You are a connectivity check. Reply with exactly: ready",
        "Connectivity check.",
        max_tokens=12,
    )
    if not reply:
        raise HTTPException(
            status_code=502,
            detail="The model did not respond. Check the base URL, key and model name.",
        )
    return {"ok": True, "model": settings.model, "provider": settings.provider, "reply": reply[:160]}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _seed_demo(target: Store) -> None:
    if target.list_datasets():
        return
    demos = [
        ("saas-revenue", "SaaS Revenue", "saas_revenue.csv"),
        ("marketing-channels", "Marketing Channels", "marketing_channels.csv"),
        ("hr-attrition", "HR Attrition", "hr_attrition.csv"),
    ]
    folder = ROOT / "datasets"
    for dataset_id, name, filename in demos:
        path = folder / filename
        if not path.exists():
            continue
        try:
            frame, meta = read_upload(filename, path.read_bytes())
            profile = build_profile(frame, dataset_id, name)
            insights = build_insights(frame, profile)
            target.save_dataset(
                dataset_id,
                name,
                frame,
                profile,
                insights,
                "demo",
                ["Bundled demo dataset."] + (meta.get("notes") or []),
            )
            log.info("Seeded demo dataset %s (%s rows)", name, f"{profile['rows']:,}")
        except Exception as exc:
            log.warning("Skipping demo %s: %s", filename, exc)


def _column(dataset: dict, name: str) -> dict:
    for col in (dataset.get("profile") or {}).get("columns") or []:
        if col["name"] == name:
            return col
    raise HTTPException(status_code=400, detail=f"No column named '{name}'.")


def _require_columns(dataset: dict, *names: str) -> None:
    for name in names:
        _column(dataset, name)


def _sql_error(exc: Exception) -> str:
    message = str(exc).strip() or type(exc).__name__
    return message[:500]


@app.exception_handler(DatasetNotFound)
def _not_found(_request, exc: DatasetNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Dataset not found."})


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
