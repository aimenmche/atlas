"""Optional LLM adapter.

Supports OpenAI-compatible endpoints and local Ollama. The deterministic engine
always remains available; when an LLM is configured it is used for SQL
generation and prose polish, with strict JSON parsing and a number-verifier on
the polished text.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .semantics import pretty
from .sqlguard import SqlRejected, validate_sql
from .util import jsonable

CHART_TYPES = {"bar", "line", "kpi", "scatter", "histogram"}
FORMATS = {"currency", "percentage", "percent_points", "count", "number", "ratio"}


class LLMClient:
    def __init__(self, settings: Any):
        self.settings = settings
        self.enabled = bool(settings.llm_enabled)

    def complete(self, system: str, user: str, max_tokens: int = 900) -> str | None:
        if not self.enabled:
            return None
        try:
            if self.settings.provider == "ollama":
                return self._ollama(system, user, max_tokens)
            return self._openai(system, user, max_tokens)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None

    def _openai(self, system: str, user: str, max_tokens: int) -> str | None:
        base = (self.settings.base_url or "https://api.openai.com/v1").rstrip("/")
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": float(self.settings.temperature),
            "max_tokens": max_tokens,
        }
        with httpx.Client(timeout=45.0) as client:
            response = client.post(f"{base}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"]

    def _ollama(self, system: str, user: str, max_tokens: int) -> str | None:
        base = (self.settings.base_url or "http://localhost:11434").rstrip("/")
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": float(self.settings.temperature), "num_predict": max_tokens},
        }
        with httpx.Client(timeout=60.0) as client:
            response = client.post(f"{base}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        return data["message"]["content"]

    # ------------------------------------------------------------------ #
    # SQL generation
    # ------------------------------------------------------------------ #
    def generate_sql(
        self,
        question: str,
        profile: dict,
        table: str,
        error: str | None = None,
    ) -> dict | None:
        if not self.enabled:
            return None
        schema = _schema_text(profile, table)
        system = (
            "You are Atlas, a senior data analyst. Translate the user's question into ONE "
            "read-only DuckDB SQL query. Return only JSON with keys: sql, title, chart_type, "
            "value_format, x_label, y_label, rationale, confidence. "
            "chart_type is one of bar, line, kpi, scatter, histogram. "
            "value_format is one of currency, percentage, percent_points, count, number, ratio. "
            "Rules: SELECT/WITH only; one statement; never query system catalogs or files; "
            "always alias grouped labels AS label and the measure AS value; quote identifiers; "
            "for time series use date_trunc and order by label; add LIMIT 500 for raw-row "
            "queries. If the question cannot be answered from these columns, return "
            '{"sql": null, "reason": "..."}.'
        )
        user = f"SCHEMA\n{schema}\n\nQUESTION\n{question}"
        if error:
            user += f"\n\nYour previous SQL failed with this error:\n{error}\nFix it."
        raw = self.complete(system, user, max_tokens=800)
        if not raw:
            return None
        data = _extract_json(raw)
        if not isinstance(data, dict) or not data.get("sql"):
            return None
        sql = str(data["sql"]).strip()
        try:
            validate_sql(sql)
        except SqlRejected:
            return None
        chart_type = data.get("chart_type") or "table"
        if chart_type not in CHART_TYPES:
            chart_type = "bar" if "GROUP BY" in sql.upper() else "table"
        value_format = data.get("value_format") or "number"
        if value_format not in FORMATS:
            value_format = "number"
        return {
            "sql": sql,
            "chart_type": chart_type,
            "title": str(data.get("title") or question),
            "rationale": str(data.get("rationale") or "Generated by the configured language model."),
            "confidence": _clamp(data.get("confidence", 0.75)),
            "value_format": value_format,
            "x_label": str(data.get("x_label") or "Label"),
            "y_label": str(data.get("y_label") or "Value"),
            "intent": "llm",
            "question": question,
            "group_expr": None,
        }

    # ------------------------------------------------------------------ #
    # Narrative polish
    # ------------------------------------------------------------------ #
    def polish(self, question: str, narrative: str, facts: dict) -> str | None:
        if not self.enabled:
            return None
        system = (
            "You are a precise data editor. Rewrite the analyst summary in at most three "
            "crisp sentences. Every number must be copied EXACTLY from the summary — never "
            "introduce, round or recompute a number. Do not add new claims, do not use bullet "
            "points, do not mention that you are an AI. Return plain text only."
        )
        user = f"QUESTION\n{question}\n\nSUMMARY\n{narrative}"
        polished = self.complete(system, user, max_tokens=260)
        if not polished:
            return None
        polished = " ".join(polished.strip().split())
        if len(polished) > 700 or not polished:
            return None
        if not _numbers_are_grounded(polished, narrative + " " + json.dumps(facts, default=str)):
            return None
        return polished


def _schema_text(profile: dict, table: str) -> str:
    lines = [f"TABLE {table} ({profile.get('rows', 0):,} rows)"]
    for col in profile.get("columns", []):
        examples = ", ".join(str(v.get("value")) for v in (col.get("top_values") or [])[:4])
        note = f"{col['semantic']} {col['role']}"
        if examples:
            note += f"; examples: {examples}"
        lines.append(f'  "{col["name"]}" { _sql_type(col) } -- {note}')
    return "\n".join(lines)


def _sql_type(col: dict) -> str:
    dtype = col.get("dtype")
    if dtype == "date":
        return "TIMESTAMP"
    if dtype in {"integer", "decimal"}:
        return "DOUBLE"
    if dtype == "boolean":
        return "BOOLEAN"
    return "VARCHAR"


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.75


def _num_tokens(text: str) -> set[str]:
    tokens = set()
    for match in re.findall(r"-?\d[\d,.]*", text):
        cleaned = match.replace(",", "").rstrip(".")
        if cleaned in {"", "-"}:
            continue
        try:
            tokens.add(f"{float(cleaned):g}")
        except ValueError:
            tokens.add(cleaned)
    return tokens


def _numbers_are_grounded(polished: str, allowed_text: str) -> bool:
    allowed = _num_tokens(allowed_text)
    return all(token in allowed for token in _num_tokens(polished))
