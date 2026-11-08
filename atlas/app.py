"""FastAPI application.

Local-first: one process, one DuckDB file, zero cloud dependencies. Uploads are
profiled on ingest, insights are stored alongside the data, and every answer
travels through the same read-only query sandbox.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .logging_setup import configure_logging
from .security import (
    AUTH_COOKIE,
    AuthRejected,
    OriginRejected,
    apply_security_headers,
    check_request_auth,
    check_request_origin,
    is_loopback_request,
    token_matches,
)
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
from .core.cohort import cohort_retention
from .core.compare import period_comparison
from .core.filters import apply_filters, serialize_filters
from .core.forecast import forecast
from .core.ingest import IngestError, inspect_upload, read_upload
from .core.profile import build_profile
from .core.relationships import correlation_matrix, lag_analysis
from .core.report import build_report
from .core.sqlguard import SqlRejected
from .core.store import DatasetNotFound, QueryTimeout, Store
from .core.util import jsonable, new_id, pretty, quote_ident, slugify

log = logging.getLogger("atlas")
configure_logging()
AUTH_TOKEN = os.environ.get("ATLAS_AUTH_TOKEN") or None

STATIC_DIR = Path(__file__).resolve().parent / "static"
UPLOAD_CHUNK_BYTES = 1024 * 1024

store: Store | None = None


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(_: FastAPI):
    global store
    ensure_dirs()
    _cleanup_partials()
    store = Store(DB_PATH)
    try:
        removed = store.purge_expired_trash(30)
        if removed:
            log.info("Purged %s expired trash item(s)", removed)
    except Exception as exc:  # cleanup must never block startup
        log.warning("Could not purge expired trash: %s", exc)
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
    # The generated Swagger and ReDoc pages load assets from a CDN. Atlas must
    # work offline, so both are disabled and the machine-readable schema stays
    # at /openapi.json. See docs/api.md for a local reference.
    docs_url=None,
    redoc_url=None,
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    request_id = (request.headers.get("x-request-id") or uuid.uuid4().hex)[:32]
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        token_param = request.query_params.get("token")
        if (
            AUTH_TOKEN
            and token_param
            and not is_loopback_request(request)
            and token_matches(token_param, AUTH_TOKEN)
        ):
            # Exchange the one-time URL token for a SameSite cookie, then remove
            # it from the address bar so it does not leak through history.
            query = dict(request.query_params)
            query.pop("token", None)
            target = request.url.path
            if query:
                target += "?" + "&".join(f"{key}={value}" for key, value in query.items())
            response = RedirectResponse(url=target, status_code=303)
            response.set_cookie(
                AUTH_COOKIE,
                AUTH_TOKEN,
                httponly=True,
                samesite="strict",
                secure=request.url.scheme == "https",
                max_age=86400 * 7,
            )
        else:
            check_request_auth(request, AUTH_TOKEN)
            check_request_origin(request)
            response = await call_next(request)
    except AuthRejected as exc:
        response = JSONResponse(
            status_code=401,
            content={"detail": str(exc)},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except OriginRejected as exc:
        response = JSONResponse(status_code=403, content={"detail": str(exc)})
    apply_security_headers(response)
    response.headers["X-Request-ID"] = request_id
    log.info(
        "%s %s %s",
        request.method,
        request.url.path,
        response.status_code,
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": round((time.perf_counter() - started) * 1000, 2),
            "client": request.client.host if request.client else "",
        },
    )
    return response


def get_store() -> Store:
    global store
    if store is None:
        ensure_dirs()
        store = Store(DB_PATH)
    return store


def get_dataset(dataset_id: str, allow_deleted: bool = False) -> dict:
    try:
        dataset = get_store().get_dataset(dataset_id)
    except DatasetNotFound:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    if dataset.get("deleted_at") and not allow_deleted:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return dataset


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


class DatasetUpdatePayload(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    tags: list[str] | None = None
    glossary: dict[str, str] | None = None


@app.post("/api/datasets/inspect")
def inspect_dataset(
    file: UploadFile = File(...),
) -> dict:
    """Describe an upload without ingesting it."""
    filename = Path(file.filename or "upload.csv").name
    temp_path, data = _spool_upload(file)
    try:
        return inspect_upload(filename, data)
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not inspect that file: {exc}")
    finally:
        _unlink(temp_path)


@app.post("/api/datasets", status_code=201)
def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    sheet: str | None = Form(default=None),
    header_row: int | None = Form(default=None),
    json_path: str | None = Form(default=None),
) -> dict:
    filename = Path(file.filename or "upload.csv").name
    temp_path, data = _spool_upload(file)
    try:
        frame, meta = read_upload(
            filename,
            data,
            sheet=(sheet or None),
            header_row=header_row,
            json_path=(json_path or None),
        )
    except IngestError as exc:
        _unlink(temp_path)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        _unlink(temp_path)
        raise HTTPException(status_code=400, detail=f"Could not read that file: {exc}")

    display = (name or "").strip() or pretty(Path(filename).stem.replace("_", " ").replace("-", " "))
    display = display[:120]
    existing = {d["id"] for d in get_store().list_datasets(include_deleted=True)}
    dataset_id = slugify(display)
    if dataset_id in existing:
        dataset_id = f"{dataset_id}-{new_id()[:5]}"

    profile = build_profile(frame, dataset_id, display)
    insights = build_insights(frame, profile)
    try:
        result = get_store().save_dataset(
            dataset_id,
            display,
            frame,
            profile,
            insights,
            meta.get("format") or "file",
            meta.get("notes") or [],
        )
    except Exception:
        _unlink(temp_path)
        raise
    try:
        # The spooled upload becomes the archived original without a second
        # full write. os.replace is atomic on the same filesystem.
        _archive_spooled(temp_path, dataset_id, filename)
    except OSError:
        log.warning("Could not archive the raw upload for %s", dataset_id)
        _unlink(temp_path)

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
def rename_dataset(dataset_id: str, payload: DatasetUpdatePayload) -> dict:
    dataset = get_dataset(dataset_id)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(
            status_code=400,
            detail="Provide a name, description, tags or glossary.",
        )
    name = values.get("name")
    if name is not None:
        name = name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="The dataset name cannot be empty.")
    description = values.get("description")
    if description is not None:
        description = description.strip()
    tags = values.get("tags")
    if tags is not None:
        if len(tags) > 12:
            raise HTTPException(status_code=400, detail="Use at most 12 tags.")
        if any(len(str(tag).strip()) > 32 for tag in tags):
            raise HTTPException(status_code=400, detail="Tags must be 32 characters or fewer.")
    glossary = values.get("glossary")
    if glossary is not None:
        columns = {str(c.get("name")) for c in (dataset.get("profile") or {}).get("columns") or []}
        unknown = [key for key in glossary if key not in columns]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown column in glossary: {unknown[0]}",
            )
        if len(glossary) > 200:
            raise HTTPException(status_code=400, detail="Use at most 200 glossary terms.")
        too_long = [key for key, value in glossary.items() if len(str(value)) > 280]
        if too_long:
            raise HTTPException(
                status_code=400,
                detail=f"Glossary definitions must be 280 characters or fewer ({too_long[0]}).",
            )
    updated = get_store().update_dataset(
        dataset_id,
        name=name,
        description=description,
        tags=tags,
        glossary=glossary,
    )
    return {
        "id": dataset_id,
        "name": updated["name"],
        "description": updated.get("description") or "",
        "tags": updated.get("tags") or [],
        "glossary": updated.get("glossary") or {},
        "previous": dataset.get("name"),
    }


@app.delete("/api/datasets/{dataset_id}")
def delete_dataset(dataset_id: str, permanent: bool = False) -> dict:
    dataset = get_dataset(dataset_id, allow_deleted=True)
    if permanent:
        get_store().purge_dataset(dataset_id)
        _delete_raw(dataset_id)
        return {"ok": True, "id": dataset_id, "permanent": True}
    get_store().trash_dataset(dataset_id)
    return {
        "ok": True,
        "id": dataset_id,
        "name": dataset.get("name"),
        "trashed": True,
        "restore_days": 30,
    }


@app.get("/api/trash")
def list_trash() -> dict:
    items = get_store().list_trash()
    return {"datasets": items, "count": len(items)}


@app.post("/api/datasets/{dataset_id}/restore")
def restore_dataset(dataset_id: str) -> dict:
    get_dataset(dataset_id, allow_deleted=True)
    restored = get_store().restore_dataset(dataset_id)
    return {"ok": True, "dataset": restored}


@app.delete("/api/trash/{dataset_id}")
def purge_trash(dataset_id: str) -> dict:
    get_dataset(dataset_id, allow_deleted=True)
    get_store().purge_dataset(dataset_id)
    _delete_raw(dataset_id)
    return {"ok": True, "id": dataset_id, "permanent": True}


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
    filters: list[dict] | None = Field(default=None, max_length=8)


@app.post("/api/datasets/{dataset_id}/query")
def run_sql(dataset_id: str, payload: QueryPayload) -> dict:
    dataset = get_dataset(dataset_id)
    settings = load_settings()
    limit = max(1, min(int(payload.limit or settings.row_limit), 5000))
    sql = apply_filters(payload.sql, dataset["table_name"], serialize_filters(payload.filters))
    try:
        return get_store().run_query(
            dataset_id,
            sql,
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
    history: list[dict] | None = Field(default=None, max_length=6)
    filters: list[dict] | None = Field(default=None, max_length=8)


@app.post("/api/datasets/{dataset_id}/ask")
def ask(dataset_id: str, payload: AskPayload) -> dict:
    get_dataset(dataset_id)
    analyst = Analyst(get_store(), load_settings())
    try:
        return analyst.ask(
            dataset_id,
            payload.question,
            history=_clean_history(payload.history),
            filters=serialize_filters(payload.filters),
        )
    except AskError as exc:
        raise HTTPException(status_code=422, detail=exc.as_dict())


@app.post("/api/datasets/{dataset_id}/ask/stream")
def ask_stream(dataset_id: str, payload: AskPayload) -> StreamingResponse:
    get_dataset(dataset_id)
    analyst = Analyst(get_store(), load_settings())

    question = payload.question
    history = _clean_history(payload.history)
    filters = serialize_filters(payload.filters)

    def frames():
        try:
            for frame in analyst.ask_stream(dataset_id, question, history=history, filters=filters):
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
    calendar: bool = True
    exclude: str | None = None
    include_anomalies: bool = True


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
            calendar=payload.calendar,
            exclude_dates=_split_dates(payload.exclude),
            include_anomalies=payload.include_anomalies,
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
    sensitivity: str | None = None,
    exclude: str | None = None,
) -> dict:
    dataset = get_dataset(dataset_id)
    _require_columns(dataset, date_col, value_col)
    frame = get_store().load_frame(dataset_id)
    level = (sensitivity or "").lower()
    if level in {"low", "medium", "high", "extreme"}:
        threshold = {"low": 4.5, "medium": 3.5, "high": 2.5, "extreme": 2.0}[level]
    try:
        result = detect_anomalies(
            frame,
            date_col,
            value_col,
            agg=agg,
            threshold=threshold,
            exclude_dates=_split_dates(exclude),
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return jsonable({
        **result,
        "sensitivity": level or "custom",
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


class ComparePayload(BaseModel):
    date_col: str
    value_col: str
    grain: str = "month"
    dimension: str | None = None
    agg: str = "sum"
    periods: int = 2


@app.post("/api/datasets/{dataset_id}/compare")
def run_comparison(dataset_id: str, payload: ComparePayload) -> dict:
    dataset = get_dataset(dataset_id)
    _require_columns(dataset, payload.date_col, payload.value_col)
    if payload.dimension:
        _require_columns(dataset, payload.dimension)
    frame = get_store().load_frame(dataset_id)
    try:
        result = period_comparison(
            frame,
            payload.date_col,
            payload.value_col,
            grain=payload.grain,
            agg=payload.agg,
            dimension=payload.dimension,
            periods=payload.periods,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    result["value_format"] = _column(dataset, payload.value_col).get("semantic")
    return jsonable(result)


class CohortPayload(BaseModel):
    entity_col: str
    date_col: str
    value_col: str | None = None
    grain: str = "month"
    periods: int = 12


@app.post("/api/datasets/{dataset_id}/cohorts")
def run_cohorts(dataset_id: str, payload: CohortPayload) -> dict:
    dataset = get_dataset(dataset_id)
    _require_columns(dataset, payload.entity_col, payload.date_col)
    if payload.value_col:
        _require_columns(dataset, payload.value_col)
    frame = get_store().load_frame(dataset_id)
    try:
        result = cohort_retention(
            frame,
            payload.entity_col,
            payload.date_col,
            value_col=payload.value_col,
            grain=payload.grain,
            periods=payload.periods,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return jsonable(result)


class RelationshipPayload(BaseModel):
    mode: str = "matrix"
    columns: list[str] | None = None
    date_col: str | None = None
    x_col: str | None = None
    y_col: str | None = None
    grain: str = "month"
    agg: str = "sum"
    max_lag: int = 6


@app.post("/api/datasets/{dataset_id}/relationships")
def run_relationships(dataset_id: str, payload: RelationshipPayload) -> dict:
    dataset = get_dataset(dataset_id)
    frame = get_store().load_frame(dataset_id)
    if payload.mode == "lag":
        if not payload.date_col or not payload.x_col or not payload.y_col:
            raise HTTPException(status_code=400, detail="Lag analysis needs date_col, x_col and y_col.")
        _require_columns(dataset, payload.date_col, payload.x_col, payload.y_col)
        try:
            return jsonable(lag_analysis(
                frame,
                payload.date_col,
                payload.x_col,
                payload.y_col,
                grain=payload.grain,
                agg=payload.agg,
                max_lag=payload.max_lag,
            ))
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    columns = payload.columns or [
        c["name"] for c in (dataset.get("profile") or {}).get("columns") or []
        if c.get("role") == "measure"
    ]
    for name in columns:
        _require_columns(dataset, name)
    try:
        return jsonable(correlation_matrix(frame, columns))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
@app.get("/api/datasets/{dataset_id}/report")
def download_report(
    dataset_id: str,
    download: bool = False,
    title: str | None = None,
    brand: str | None = None,
    sections: str | None = None,
    template: str = "full",
    redact: bool | None = None,
):
    dataset = get_dataset(dataset_id)
    settings = load_settings()
    selected = [part.strip() for part in sections.split(",")] if sections else None
    needs_forecast = template == "forecast" or bool(selected and "forecast" in selected)
    forecast_result = _report_forecast(dataset) if needs_forecast else None
    html = build_report(
        dataset,
        redact=settings.redact_pii if redact is None else redact,
        title=title,
        brand=brand,
        sections=selected,
        template=template,
        forecast=forecast_result,
    )
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
    max_tokens_per_request: int | None = None
    cost_budget_usd: float | None = None
    input_cost_per_1k: float | None = None
    output_cost_per_1k: float | None = None
    redact_pii: bool | None = None


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
    if "max_tokens_per_request" in values and values["max_tokens_per_request"] is not None:
        current.max_tokens_per_request = max(500, min(200_000, int(values["max_tokens_per_request"])))
    if "cost_budget_usd" in values and values["cost_budget_usd"] is not None:
        current.cost_budget_usd = max(0.0, min(100.0, float(values["cost_budget_usd"])))
    if "input_cost_per_1k" in values and values["input_cost_per_1k"] is not None:
        current.input_cost_per_1k = max(0.0, min(100.0, float(values["input_cost_per_1k"])))
    if "output_cost_per_1k" in values and values["output_cost_per_1k"] is not None:
        current.output_cost_per_1k = max(0.0, min(100.0, float(values["output_cost_per_1k"])))
    if "redact_pii" in values and values["redact_pii"] is not None:
        current.redact_pii = bool(values["redact_pii"])
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


def _report_forecast(dataset: dict) -> dict:
    """Build a default forecast for the report without failing the export."""
    profile = dataset.get("profile") or {}
    time_info = profile.get("time") or {}
    date_column = time_info.get("column")
    measures = [
        column
        for column in (profile.get("columns") or [])
        if column.get("role") == "measure" and not column.get("pii")
    ]
    if not date_column or not measures:
        return {
            "error": (
                "This dataset needs a detected time column and a numeric measure "
                "before Atlas can add a forecast section."
            )
        }
    try:
        result = forecast(
            get_store().load_frame(dataset["id"]),
            date_column,
            measures[0]["name"],
            horizon=6,
            agg="sum",
            calendar=True,
            include_anomalies=True,
        )
        result["value_format"] = measures[0].get("semantic") or "number"
        return jsonable(result)
    except Exception as exc:  # a report must still export when a series is too short
        log.warning("Could not build report forecast for %s: %s", dataset["id"], exc)
        return {"error": f"Forecast unavailable for this dataset: {exc}"}


def _sql_error(exc: Exception) -> str:
    message = str(exc).strip() or type(exc).__name__
    return message[:500]


def _split_dates(value: str | None) -> list[str]:
    if not value:
        return []
    parts = [part.strip() for part in value.replace(";", ",").split(",")]
    return [part for part in parts if part][:60]


def _clean_history(history: list[dict] | None) -> list[dict]:
    """Only keep the fields the analyst may use as conversational context."""
    out: list[dict] = []
    for turn in (history or [])[-6:]:
        if not isinstance(turn, dict):
            continue
        question = " ".join(str(turn.get("question") or "").split())[:500]
        if not question:
            continue
        out.append({"question": question})
    return out


def _spool_upload(file: UploadFile) -> tuple[Path, bytes]:
    """Copy an upload to a bounded temp file in chunks.

    Starlette already spools large multipart bodies to disk. Copying in chunks
    here enforces the size cap while reading, keeps peak memory bounded by the
    file size rather than twice the file size, and gives the upload route an
    atomic archive candidate.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    total = 0
    try:
        with tempfile.NamedTemporaryFile(
            dir=RAW_DIR, prefix=".upload-", suffix=".part", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            while True:
                chunk = file.file.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            "File exceeds the "
                            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit."
                        ),
                    )
                handle.write(chunk)
            if total == 0:
                raise HTTPException(status_code=400, detail="The uploaded file is empty.")
            handle.flush()
            os.fsync(handle.fileno())
        return temp_path, temp_path.read_bytes()
    except Exception:
        _unlink(temp_path)
        raise


def _archive_spooled(temp_path: Path, dataset_id: str, filename: str) -> None:
    """Move a spooled upload into the raw archive atomically."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.lower()[:8]
    destination = RAW_DIR / f"{dataset_id}{suffix}"
    os.replace(temp_path, destination)


def _unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _delete_raw(dataset_id: str) -> None:
    for candidate in RAW_DIR.glob(f"{dataset_id}.*"):
        try:
            candidate.unlink()
        except OSError:
            pass


def _cleanup_partials() -> None:
    for partial in RAW_DIR.glob(".*.part"):
        try:
            partial.unlink()
        except OSError:
            pass


@app.exception_handler(DatasetNotFound)
def _not_found(_request, exc: DatasetNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Dataset not found."})


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
