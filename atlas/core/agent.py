"""The analyst loop.

Deterministic-first: the rule-based NL→SQL engine answers most questions with
no model and no network. When that engine cannot parse a question and a model
is configured, the model proposes SQL through a narrow JSON contract. Either
way the query runs in the read-only sandbox, and the narrative is generated
from the returned rows — never from the model's imagination.

``ask`` is the synchronous pipeline; ``ask_stream`` emits the same steps as
server-sent events so the interface can show its work.
"""
from __future__ import annotations

import math
import re
import time
from typing import Any, Iterator

from . import nlsql, stats
from .llm import LLMClient
from .narrator import narrate
from .semantics import pretty
from .store import DatasetNotFound, QueryTimeout, Store
from .util import jsonable, pretty_period


class AskError(RuntimeError):
    """A question that could not be turned into a trustworthy answer."""

    def __init__(
        self,
        message: str,
        hint: str | None = None,
        detail: str | None = None,
        sql: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.detail = detail
        self.sql = sql

    def as_dict(self) -> dict:
        return {
            "error": self.message,
            "hint": self.hint,
            "detail": self.detail,
            "sql": self.sql,
        }


class Analyst:
    def __init__(self, store: Store, settings: Any):
        self.store = store
        self.settings = settings

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def ask(self, dataset_id: str, question: str) -> dict:
        answer, _ = self._run(dataset_id, question, emit=None)
        return answer

    def ask_stream(self, dataset_id: str, question: str) -> Iterator[dict]:
        """Yield ``{"event": ..., "data": ...}`` frames.

        The final frames are ``answer`` (the complete payload) and ``done``.
        Any failure arrives as a single ``error`` frame — the HTTP response has
        already started, so errors must travel in-band.
        """
        frames: list[dict] = []

        def emit(event: str, data: dict) -> None:
            frames.append({"event": event, "data": data})

        try:
            answer, _ = self._run(dataset_id, question, emit=emit)
        except AskError as exc:
            for frame in frames:
                yield frame
            yield {"event": "error", "data": exc.as_dict()}
            return
        except Exception as exc:  # pragma: no cover - defensive
            for frame in frames:
                yield frame
            yield {
                "event": "error",
                "data": {
                    "error": "The analysis engine hit an unexpected error.",
                    "hint": "Try a simpler question, or re-upload the dataset.",
                    "detail": f"{type(exc).__name__}: {exc}",
                },
            }
            return
        for frame in frames:
            yield frame
        yield {"event": "answer", "data": answer}
        yield {"event": "done", "data": {"ok": True, "ms": answer["elapsed_ms"]}}

    # ------------------------------------------------------------------ #
    # Pipeline
    # ------------------------------------------------------------------ #
    def _run(self, dataset_id: str, question: str, emit) -> tuple[dict, dict | None]:
        started = time.perf_counter()
        question = " ".join(str(question or "").split()).strip()
        if not question:
            raise AskError("Ask a question about the dataset.", "For example: revenue by region.")
        if len(question) > 500:
            raise AskError("That question is too long.", "Keep it under 500 characters.")

        try:
            dataset = self.store.get_dataset(dataset_id)
        except DatasetNotFound:
            raise AskError("That dataset no longer exists.", "Pick another dataset from the sidebar.")
        profile = dataset.get("profile") or {}
        if not profile.get("columns"):
            raise AskError("This dataset has no readable columns.", "Try re-uploading the file.")
        table = dataset["table_name"]
        trace: list[dict] = []

        def step(stage: str, label: str, detail: str | None = None, **extra) -> None:
            entry = {
                "stage": stage,
                "label": label,
                "detail": detail,
                "ms": round((time.perf_counter() - started) * 1000, 1),
            }
            entry.update({k: v for k, v in extra.items() if v is not None})
            trace.append(entry)
            if emit:
                emit("step", entry)

        step("understand", "Read the question", question)
        settings = self.settings
        client = LLMClient(settings)
        engine = "deterministic"
        parsed: dict | None = None
        result: dict | None = None
        last_error: str | None = None

        # ---- plan ------------------------------------------------------ #
        try:
            parsed = nlsql.parse_question(question, profile, table)
        except Exception as exc:  # a parser bug must not take the app down
            last_error = f"{type(exc).__name__}: {exc}"
            parsed = None
        if parsed:
            step(
                "plan",
                "Built a query plan",
                parsed.get("rationale") or parsed.get("title"),
                engine="deterministic",
                confidence=parsed.get("confidence"),
            )
        else:
            step("plan", "No deterministic plan", "Falling back to the configured language model." if client.enabled else "The rule-based parser did not recognise this question.")

        # ---- execute, with one repair attempt -------------------------- #
        attempts = 0
        if parsed:
            attempts += 1
            try:
                result = self._execute(dataset_id, parsed["sql"], settings)
                step(
                    "execute",
                    "Ran the query",
                    f"{result['row_count']:,} rows in {result['elapsed_ms']:,} ms",
                    sql=parsed["sql"],
                    engine=engine,
                )
            except (QueryTimeout, Exception) as exc:
                last_error = _error_text(exc)
                step("execute", "Query failed", last_error, sql=parsed["sql"], status="error")

        if result is None and client.enabled:
            engine = "llm"
            error_for_model = last_error
            for repair in range(2):
                attempts += 1
                proposal = None
                try:
                    proposal = client.generate_sql(question, profile, table, error=error_for_model)
                except Exception as exc:  # pragma: no cover - adapter is defensive
                    last_error = _error_text(exc)
                    break
                if not proposal:
                    last_error = last_error or "The language model did not return usable SQL."
                    break
                parsed = proposal
                step(
                    "plan",
                    "Model proposed a query" + (" (repaired)" if repair else ""),
                    proposal.get("rationale"),
                    sql=proposal["sql"],
                    engine="llm",
                    confidence=proposal.get("confidence"),
                )
                try:
                    result = self._execute(dataset_id, proposal["sql"], settings)
                    step(
                        "execute",
                        "Ran the query",
                        f"{result['row_count']:,} rows in {result['elapsed_ms']:,} ms",
                        sql=proposal["sql"],
                        engine="llm",
                    )
                    break
                except Exception as exc:
                    last_error = _error_text(exc)
                    error_for_model = last_error
                    step("execute", "Query failed", last_error, sql=proposal["sql"], status="error")

        if result is None or parsed is None:
            dims = [pretty(c["name"]) for c in profile.get("columns", []) if c["role"] == "dimension"]
            measures = [pretty(c["name"]) for c in profile.get("columns", []) if c["role"] == "measure"]
            if client.enabled:
                hint = "Try a simpler phrasing, or pick a stronger model in Settings."
            elif dims and measures:
                hint = (
                    f"Try grouping a measure by a column, for example “{measures[0].lower()} by {dims[0].lower()}”. "
                    f"This dataset can be grouped by {', '.join(dims[:4])}."
                )
            elif dims:
                hint = f"Try asking about one of: {', '.join(dims[:5])}."
            else:
                hint = "Try naming a column that exists in this dataset."
            raise AskError(
                "I could not turn that into a reliable query.",
                hint,
                detail=last_error,
                sql=(parsed or {}).get("sql"),
            )

        # ---- shape the answer ----------------------------------------- #
        rows = result.get("rows") or []
        if not rows:
            step("shape", "No matching rows", "The query was valid but returned nothing.")

        chart = build_chart(parsed, result, profile)
        chart_labels = {
            "bar": "Bar chart",
            "line": "Line chart",
            "scatter": "Scatter plot",
            "histogram": "Histogram",
            "kpi": "KPI card",
            "table": "Table",
            "empty": "No visual",
        }
        step("shape", "Built the visual", chart_labels.get(chart.get("type"), "Table"))

        narration = narrate(question, parsed, result, profile)
        polished = False
        if client.enabled and narration.get("narrative") and rows:
            try:
                better = client.polish(question, narration["narrative"], narration.get("facts") or {})
                if better and better != narration["narrative"]:
                    narration["narrative"] = better
                    polished = True
            except Exception:  # polish is strictly optional
                pass
        step(
            "narrate",
            "Wrote the summary",
            "Polished by the configured model — every number verified against the result." if polished else "Grounded in the returned rows.",
            polished=polished,
        )

        followups = _followups(profile, table, parsed, question)
        confidence = _confidence(parsed, result, profile)
        step(
            "finish",
            "Ready",
            f"{attempts} query attempt{'s' if attempts != 1 else ''}",
            confidence=confidence["score"],
        )

        elapsed = round((time.perf_counter() - started) * 1000, 1)
        answer = {
            "dataset_id": dataset_id,
            "dataset": dataset.get("name"),
            "question": question,
            "engine": engine,
            "llm_used": engine == "llm",
            "polished": polished,
            "plan": {
                "title": parsed.get("title") or question,
                "rationale": parsed.get("rationale"),
                "intent": parsed.get("intent"),
                "confidence": parsed.get("confidence"),
                "chart_type": parsed.get("chart_type"),
                "x_label": parsed.get("x_label"),
                "y_label": parsed.get("y_label"),
                "value_format": parsed.get("value_format") or "number",
                "grain": parsed.get("grain"),
            },
            "sql": result.get("sql") or parsed.get("sql"),
            "result": result,
            "chart": chart,
            "narrative": narration.get("narrative"),
            "highlights": narration.get("highlights") or [],
            "caveats": narration.get("caveats") or [],
            "facts": narration.get("facts") or {},
            "followups": followups,
            "confidence": confidence,
            "trace": trace,
            "attempts": attempts,
            "elapsed_ms": elapsed,
        }
        return answer, parsed

    # ------------------------------------------------------------------ #
    def _execute(self, dataset_id: str, sql: str, settings: Any) -> dict:
        return self.store.run_query(
            dataset_id,
            sql,
            timeout=float(getattr(settings, "query_timeout", 8.0) or 8.0),
            limit=int(getattr(settings, "row_limit", 1000) or 1000),
        )


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def build_chart(parsed: dict, result: dict, profile: dict) -> dict:
    """Turn a query result into a compact chart spec the browser can render."""
    chart_type = parsed.get("chart_type") or "table"
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    fmt = parsed.get("value_format") or "number"
    x_label = parsed.get("x_label") or (columns[0] if columns else "Label")
    y_label = parsed.get("y_label") or (columns[1] if len(columns) > 1 else "Value")

    if not rows:
        return {"type": "empty", "message": "No rows matched this question."}

    if chart_type == "kpi":
        return {
            "type": "kpi",
            "value": rows[0][0] if rows[0] else None,
            "label": parsed.get("title") or y_label,
            "format": fmt,
            "x_label": x_label,
            "y_label": y_label,
        }

    if chart_type in {"bar", "line"}:
        if len(columns) < 2:
            return _table_chart(columns, rows)
        labels: list[str] = []
        values: list[float | None] = []
        for row in rows:
            label = row[0]
            label = "—" if label is None else str(label)
            if parsed.get("grain"):
                label = pretty_period(label, parsed.get("grain"))
            labels.append(label)
            values.append(_number(row[1]))
        keep = 400 if chart_type == "line" else 30
        if len(labels) > keep:
            labels, values = labels[:keep], values[:keep]
        if chart_type == "bar":
            pairs = sorted(
                ((lab, val) for lab, val in zip(labels, values) if val is not None),
                key=lambda p: p[1],
                reverse=True,
            )
            labels = [p[0] for p in pairs]
            values = [p[1] for p in pairs]
            if not labels:
                return _table_chart(columns, rows)
        total = sum(v for v in values if v is not None)
        return {
            "type": chart_type,
            "labels": labels,
            "values": values,
            "format": fmt,
            "x_label": x_label,
            "y_label": y_label,
            "horizontal": chart_type == "bar" and (len(labels) > 7 or _long_labels(labels)),
            "total": total if fmt in {"currency", "count", "number"} else None,
            "grain": parsed.get("grain"),
        }

    if chart_type == "scatter":
        idx = _numeric_pair(rows)
        if idx is None:
            return _table_chart(columns, rows)
        xi, yi = idx
        points = []
        for row in rows:
            x, y = _number(row[xi]), _number(row[yi])
            if x is not None and y is not None:
                points.append([x, y])
        if len(points) > 1200:
            step = len(points) / 1200
            points = [points[int(i * step)] for i in range(1200)]
        return {
            "type": "scatter",
            "points": points,
            "x_label": parsed.get("x_label") or columns[xi],
            "y_label": parsed.get("y_label") or columns[yi],
            "x_format": parsed.get("x_format") or "number",
            "y_format": parsed.get("y_format") or "number",
            "n": len(points),
        }

    if chart_type == "histogram":
        values = [_number(row[0]) for row in rows if row]
        values = [v for v in values if v is not None]
        if len(values) < 3:
            return _table_chart(columns, rows)
        hist = stats.histogram(values, max_bins=28)
        desc = stats.describe(values)
        return {
            "type": "histogram",
            "counts": hist["counts"],
            "edges": hist["edges"],
            "labels": hist["labels"],
            "format": fmt,
            "x_label": parsed.get("x_label") or columns[0],
            "y_label": "Rows",
            "stats": {k: _round(v) for k, v in desc.items() if k in {"median", "p25", "p75", "mean", "min", "max", "skew"}},
        }

    return _table_chart(columns, rows)


def _table_chart(columns: list[str], rows: list[list[Any]]) -> dict:
    return {
        "type": "table",
        "columns": columns,
        "rows": [[jsonable(v) for v in row] for row in rows[:100]],
        "truncated": len(rows) > 100,
    }


def _numeric_pair(rows: list[list[Any]]) -> tuple[int, int] | None:
    width = max((len(r) for r in rows), default=0)
    numeric = []
    for i in range(width):
        values = [_number(r[i]) for r in rows if i < len(r)]
        good = [v for v in values if v is not None]
        if len(good) >= max(3, len(values) * 0.6):
            numeric.append(i)
        if len(numeric) == 2:
            return numeric[0], numeric[1]
    if len(numeric) >= 2:
        return numeric[0], numeric[1]
    return None


def _long_labels(labels: list[str]) -> bool:
    return any(len(label) > 18 for label in labels)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 3) if math.isfinite(value) else None
    return value


# --------------------------------------------------------------------------- #
# Follow-ups
# --------------------------------------------------------------------------- #
def _followups(profile: dict, table: str, parsed: dict, question: str) -> list[str]:
    columns = profile.get("columns") or []
    dims = [c for c in columns if c["role"] == "dimension" and c["semantic"] not in {"date", "datetime"}]
    dims.sort(key=lambda c: (
        0 if c["semantic"] == "category" else 1 if c["semantic"] == "ordinal" else 2,
        c.get("distinct", 999),
    ))
    dims = [c for c in dims if 1 < c.get("distinct", 0) <= 30]
    measures = [c for c in columns if c["role"] == "measure"]
    measures.sort(key=lambda c: 0 if c.get("semantic") == "currency" else 1)
    time_col = (profile.get("time") or {}).get("column")

    # Prefer the columns this answer actually used, so follow-ups continue the
    # thread instead of restarting from the same generic default.
    title = (parsed.get("title") or "").lower()
    x_label = (parsed.get("x_label") or "").lower()
    y_label = (parsed.get("y_label") or "").lower()
    measure = _mentioned(measures, y_label, title) or (measures[0] if measures else None)
    used_dim = _mentioned(dims, x_label, title)
    outcome = _mentioned([c for c in columns if c["semantic"] == "boolean"], y_label, title)
    if used_dim:
        dims = [used_dim] + [d for d in dims if d["name"] != used_dim["name"]]
    dim = next((d for d in dims if d["semantic"] != "boolean"), dims[0] if dims else None)
    alt_dim = next(
        (d for d in dims if d["semantic"] != "boolean" and (not used_dim or d["name"] != used_dim["name"])),
        None,
    )
    alt_measure = next(
        (m for m in measures if m["semantic"] != "count" and (not measure or m["name"] != measure["name"])),
        None,
    ) or next((m for m in measures if not measure or m["name"] != measure["name"]), None)

    m_label = pretty(measure["name"]).lower() if measure else "records"
    d_label = pretty(dim["name"]).lower() if dim else None
    alt_d_label = pretty(alt_dim["name"]).lower() if alt_dim else None
    alt_m_label = pretty(alt_measure["name"]).lower() if alt_measure else None
    has_time = bool(time_col and measure)

    candidates: list[str] = []
    intent = parsed.get("intent") or ""

    if outcome:
        o_label = f"{pretty(outcome['name']).lower()} rate"
        if d_label:
            candidates.append(f"Which {d_label} has the highest {o_label}?")
        if time_col:
            candidates.append(f"How has {o_label} changed over time?")
        if alt_d_label:
            candidates.append(f"Show {o_label} by {alt_d_label}")
        candidates.append("How many rows are there?")
    elif intent in {"correlation"}:
        if has_time:
            candidates.append(f"How has {m_label} changed over time?")
        if d_label:
            candidates.append(f"Which {d_label} has the highest average {m_label}?")
        candidates.append(f"Show {m_label} distribution")
    elif intent == "distribution":
        if has_time:
            candidates.append(f"How has {m_label} changed over time?")
        if d_label:
            candidates.append(f"Which {d_label} has the highest average {m_label}?")
        if alt_m_label:
            candidates.append(f"What is the correlation between {m_label} and {alt_m_label}?")
    elif intent in {"trend", "rate_trend"}:
        if d_label:
            candidates.append(f"Which {d_label} has the highest {m_label}?")
        if alt_d_label:
            candidates.append(f"Show {m_label} by {alt_d_label}")
        candidates.append(f"Show {m_label} distribution")
        if alt_m_label:
            candidates.append(f"How has {alt_m_label} changed over time?")
    else:
        if has_time:
            candidates.append(f"How has {m_label} changed over time?")
        if d_label:
            candidates.append(f"Which {d_label} has the highest average {m_label}?")
            if used_dim and alt_d_label:
                candidates.append(f"Show {m_label} by {alt_d_label}")
        if alt_m_label:
            candidates.append(f"What is the correlation between {m_label} and {alt_m_label}?")
        candidates.append(f"Show {m_label} distribution")

    candidates.append("How many rows are there?")

    out: list[str] = []
    seen = {_key(question)}
    for candidate in candidates:
        key = _key(candidate)
        if key in seen:
            continue
        try:
            if nlsql.parse_question(candidate, profile, table) is None:
                continue
        except Exception:
            continue
        seen.add(key)
        out.append(candidate)
        if len(out) == 4:
            break
    return out


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).lower()).strip(" ?.!")


def _mentioned(columns: list[dict], *texts: str) -> dict | None:
    for text in texts:
        if not text:
            continue
        for col in columns:
            if pretty(col["name"]).lower() in text or col["name"].lower() in text:
                return col
    return None


# --------------------------------------------------------------------------- #
# Confidence & errors
# --------------------------------------------------------------------------- #
def _confidence(parsed: dict, result: dict, profile: dict) -> dict:
    score = float(parsed.get("confidence") or 0.75)
    rows = result.get("row_count") or 0
    if rows == 0:
        score = 0.0
    elif result.get("truncated"):
        score *= 0.95
    quality = (profile.get("quality") or {}).get("score")
    if isinstance(quality, (int, float)):
        score *= 0.75 + min(1.0, max(0.0, quality / 100)) * 0.25
    score = round(max(0.0, min(1.0, score)), 2)
    label = "high" if score >= 0.8 else "medium" if score >= 0.6 else "low" if score > 0 else "none"
    note = None
    if rows == 0:
        note = "No rows matched."
    elif result.get("truncated"):
        note = "Result truncated at the row limit."
    elif isinstance(quality, (int, float)) and quality < 70:
        note = f"Data quality is {quality:.0f}/100."
    return {"score": score, "label": label, "note": note}


def _error_text(exc: Exception) -> str:
    if isinstance(exc, QueryTimeout):
        return str(exc)
    text = str(exc).strip()
    if not text:
        return type(exc).__name__
    if len(text) > 400:
        text = text[:400] + "…"
    return text
