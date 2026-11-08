"""Deterministic natural-language → SQL.

This is Atlas's no-API-key analyst. It resolves columns by name, label and
synonym, understands aggregations, grouping, filters, time grains, top-N,
shares, distributions and correlations, then emits validated read-only SQL.
The LLM path (``llm.py``) is used first when configured; this is the fallback
and the benchmark baseline.
"""
from __future__ import annotations

import difflib
import re

from .semantics import pretty
from .sqlguard import validate_sql
from .util import quote_ident, quote_literal

SYNONYMS: dict[str, list[str]] = {
    "revenue": ["revenue", "sales", "mrr", "arr", "turnover", "billing", "bookings"],
    "spend": ["spend", "spent", "cost", "costs", "budget", "ad spend", "marketing spend"],
    "churn_rate": ["churn", "churn rate", "attrition rate", "cancel rate"],
    "support_tickets": ["tickets", "support tickets", "support", "cases"],
    "nps": ["nps", "net promoter", "satisfaction score", "promoter"],
    "trial_signups": ["trials", "signups", "sign ups", "trial signups"],
    "customers": ["customers", "accounts", "clients"],
    "seats": ["seats", "licenses", "licences", "users", "active users", "seats sold"],
    "monthly_income": ["income", "salary", "salaries", "pay", "compensation", "monthly income"],
    "tenure_years": ["tenure", "years at company", "seniority"],
    "satisfaction": ["satisfaction", "satisfied", "morale"],
    "attrition": ["attrition", "turnover", "leaving", "resignation", "resigned"],
    "overtime": ["overtime", "over time", "extra hours"],
    "department": ["department", "dept", "team", "function"],
    "job_role": ["role", "job role", "title", "position"],
    "region": ["region", "regions", "geography", "market", "area"],
    "segment": ["segment", "segments", "tier", "customer type"],
    "plan": ["plan", "plans", "package", "subscription"],
    "channel": ["channel", "channels", "source", "medium"],
    "date": ["date", "day", "time", "period"],
    "week": ["week", "weekly"],
}

AGG_WORDS = {
    "sum": ["total", "sum", "combined", "overall", "aggregate"],
    "avg": ["average", "avg", "mean", "typical", "per record"],
    "max": ["maximum", "max", "highest", "largest", "most", "peak"],
    "min": ["minimum", "min", "lowest", "smallest", "least", "bottom"],
    "count": ["count", "number of", "how many"],
}
STOPWORDS = {
    "the", "a", "an", "of", "for", "in", "on", "by", "per", "to", "and", "or", "is",
    "are", "was", "were", "what", "which", "who", "show", "me", "please", "give", "get",
    "display", "do", "does", "did", "with", "from", "across", "each", "their", "its",
    "has", "have", "had", "that", "this", "there", "how", "many", "much", "we", "our",
}


def parse_question(question: str, profile: dict, table: str) -> dict | None:
    q = _normalize(question)
    if not q:
        return None
    columns = profile.get("columns", [])
    measures = [c for c in columns if c["role"] == "measure"]
    dims = [c for c in columns if c["role"] == "dimension" and c["semantic"] not in {"date", "datetime"}]
    times = [c for c in columns if c["role"] == "time"]
    time_col = (profile.get("time") or {}).get("column")
    if not time_col and times:
        time_col = times[0]["name"]
    t = quote_ident(table)

    # Forecasting is handled by the dedicated Forecast studio, not by a
    # one-shot aggregate; refuse rather than return a misleading total.
    if re.search(r"\b(forecast|project|predict)\b", q) or (
        time_col and re.search(r"\bnext\s+\d+\s+(day|week|month|quarter|year)s?\b", q)
    ):
        return None

    # ---- row count -------------------------------------------------------
    if re.search(r"\b(how many (rows|records|entries|observations)|row count|count rows)\b", q):
        row_dim = _dimension_for_question(q, dims)
        if row_dim:
            dim_expr = _dim_expr(row_dim)
            sql = (
                f"SELECT {dim_expr} AS label, COUNT(*) AS value FROM {t} "
                f"WHERE {quote_ident(row_dim['name'])} IS NOT NULL "
                f"GROUP BY label ORDER BY value DESC"
            )
            return _answer(
                sql, "bar", dim_expr,
                f"Rows by {pretty(row_dim['name']).lower()}",
                f"Counted rows for each {pretty(row_dim['name']).lower()}.",
                0.92, "count_by", question,
                value_format="number", x_label=pretty(row_dim["name"]), y_label="Rows",
            )
        return _answer(
            f"SELECT COUNT(*) AS value FROM {t}",
            "kpi",
            None,
            "Records in dataset",
            "Counted every row in the dataset.",
            0.98,
            "count",
            question,
        )

    # ---- correlation -----------------------------------------------------
    if re.search(r"\b(correlat|relationship|related|association)\w*\b", q):
        pair = _two_measures(q, measures)
        if pair:
            a, b = pair
            sql = (
                f"SELECT {quote_ident(a['name'])}, {quote_ident(b['name'])} FROM {t} "
                f"WHERE {quote_ident(a['name'])} IS NOT NULL AND {quote_ident(b['name'])} IS NOT NULL"
            )
            return _answer(
                sql, "scatter", None,
                f"{pretty(a['name'])} vs {pretty(b['name'])}",
                f"Selected both numeric columns to measure their relationship.",
                0.85, "correlation", question,
                x_label=pretty(a["name"]), y_label=pretty(b["name"]),
                x_format=a["semantic"], y_format=b["semantic"],
            )

    # ---- two-measure comparison -----------------------------------------
    if re.search(r"\b(compare|comparison|versus|vs)\b", q) and not _dimension_for_question(q, dims):
        pair = _two_measures(q, measures)
        if pair:
            a, b = pair
            sql = (
                f"SELECT {quote_ident(a['name'])}, {quote_ident(b['name'])} FROM {t} "
                f"WHERE {quote_ident(a['name'])} IS NOT NULL AND {quote_ident(b['name'])} IS NOT NULL"
            )
            return _answer(
                sql, "scatter", None,
                f"{pretty(a['name'])} vs {pretty(b['name'])}",
                f"Compared both numeric columns on the same rows.",
                0.84, "comparison", question,
                x_label=pretty(a["name"]), y_label=pretty(b["name"]),
                x_format=a["semantic"], y_format=b["semantic"],
            )

    # ---- distribution ----------------------------------------------------
    if re.search(r"\b(distribution|histogram|spread|dispersion)\b", q):
        measure = _best_column(q, measures)
        if measure:
            sql = f"SELECT {quote_ident(measure['name'])} FROM {t} WHERE {quote_ident(measure['name'])} IS NOT NULL"
            return _answer(
                sql, "histogram", None,
                f"Distribution of {pretty(measure['name'])}",
                f"Pulled raw values to show the distribution of {pretty(measure['name'])}.",
                0.85, "distribution", question,
                value_format=measure["semantic"], x_label=pretty(measure["name"]),
            )

    measure = _best_column(q, measures)
    dim = _dimension_for_question(q, dims)
    share = bool(re.search(r"\b(share|percentage|percent of|proportion|split)\b", q))
    if dim and not _explicit_group(q) and not share and not re.search(r"\b(which|compare|versus|vs)\b", q):
        dim = None
    booleans = [c for c in columns if c["semantic"] == "boolean"]
    outcome = _best_column(q, booleans, threshold=0.7)
    if outcome and dim and outcome["name"] == dim["name"]:
        dim = None
    time_intent = _time_intent(q)
    if time_intent and not time_col and re.search(r"\b(over time|trend|time series)\b", q):
        return None
    grain = _grain(q)
    values = _value_filters(q, dims)
    exclusions = _exclusion_filters(q, dims)
    # A value can only be included or excluded, never both.
    for name, excluded in exclusions.items():
        drop = {v.strip().lower() for v in excluded}
        values[name] = [v for v in values.get(name, []) if v.strip().lower() not in drop]
        if not values[name]:
            values.pop(name, None)
    if share and dim:
        # A share needs the full denominator, so don't filter the grouped category.
        values.pop(dim["name"], None)
        exclusions.pop(dim["name"], None)
    top_n = _top_n(q)
    agg = _aggregation(q, measure, time_intent, has_dim=dim is not None)
    if top_n and agg in {"max", "min"}:
        agg = "sum" if measure and measure["semantic"] in {"currency", "count"} else "avg"
    order_dir = "ASC" if re.search(r"\b(lowest|smallest|least|bottom|worst)\b", q) else "DESC"

    where: list[str] = []
    if measure:
        where.append(f"{quote_ident(measure['name'])} IS NOT NULL")
    where.extend(_numeric_filters(q, measures))
    where.extend(_time_filters(q, time_col, t))
    for col, vals in values.items():
        where.append(_value_clause(col, vals))
    for col, vals in exclusions.items():
        where.append(_exclusion_clause(col, vals))

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    # A grouping request that names a column we don't have must fail loudly,
    # not silently fall back to a grand total.
    if _unresolved_group(q, dims, measures):
        return None
    # Two simultaneous breakdowns need a cross-tab; answering with one of them
    # would be a confident half-truth.
    if _multiple_group_request(q, dims, time_col):
        return None

    # ---- boolean outcome rates ------------------------------------------
    if outcome:
        expr = f"ROUND(100.0 * AVG(CASE WHEN CAST({quote_ident(outcome['name'])} AS BOOLEAN) THEN 1 ELSE 0 END), 2)"
        if dim:
            sql = (
                f"SELECT {_dim_expr(dim)} AS label, {expr} AS value FROM {t}{where_sql} "
                f"GROUP BY label ORDER BY value DESC"
            )
            return _answer(
                sql, "bar", None,
                f"{pretty(outcome['name'])} rate by {pretty(dim['name']).lower()}",
                f"Computed the {pretty(outcome['name']).lower()} rate for each {pretty(dim['name']).lower()}.",
                0.88, "rate", question,
                value_format="percent_points",
                x_label=pretty(dim["name"]), y_label=f"{pretty(outcome['name'])} rate",
            )
        if time_intent and time_col:
            sql = (
                f"SELECT date_trunc('{grain}', {quote_ident(time_col)}) AS label, {expr} AS value "
                f"FROM {t}{where_sql} GROUP BY label ORDER BY label ASC"
            )
            return _answer(
                sql, "line", None,
                f"{pretty(outcome['name'])} rate over time",
                f"Computed the {pretty(outcome['name']).lower()} rate by {grain}.",
                0.85, "rate_trend", question,
                value_format="percent_points",
                x_label=pretty(time_col), y_label=f"{pretty(outcome['name'])} rate",
            )
        sql = f"SELECT {expr} AS value FROM {t}{where_sql}"
        return _answer(
            sql, "kpi", None,
            f"{pretty(outcome['name'])} rate",
            f"Computed the overall {pretty(outcome['name']).lower()} rate.",
            0.85, "rate", question,
            value_format="percent_points", x_label=f"{pretty(outcome['name'])} rate",
        )

    # ---- year/quarter over previous -------------------------------------
    comparison = _comparison_intent(q)
    if comparison and time_col and measure:
        comp_grain, lag, is_yoy = comparison
        label_expr = f"date_trunc('{comp_grain}', {quote_ident(time_col)})"
        value_expr = _agg_expr(agg, measure)
        sql = (
            f"WITH base AS ("
            f"SELECT {label_expr} AS label, {value_expr} AS value FROM {t}{where_sql} "
            f"GROUP BY label),"
            f" compared AS (SELECT label, value, LAG(value, {lag}) OVER (ORDER BY label) AS prior FROM base)"
            f" SELECT label, value, prior, "
            f"ROUND(100.0 * (value - prior) / NULLIF(prior, 0), 2) AS change_pct "
            f"FROM compared ORDER BY label ASC"
        )
        if is_yoy:
            title = f"{pretty(measure['name'])} year over year"
            if comp_grain == "month":
                title += " by month"
            rationale = "Compared each month with the same month a year earlier."
        else:
            unit = {"quarter": "quarter over quarter", "month": "month over month", "week": "week over week"}.get(
                comp_grain, "period over period"
            )
            title = f"{pretty(measure['name'])} {unit}"
            rationale = f"Compared each {comp_grain} with the immediately preceding {comp_grain}."
        return _answer(
            sql, "line", label_expr, title, rationale,
            0.87, "yoy" if is_yoy else "period_compare", question,
            value_format=measure["semantic"],
            x_label=pretty(time_col), y_label=pretty(measure["name"]),
            grain=comp_grain,
        )

    # ---- time series -----------------------------------------------------
    # "Revenue by month" is a time series, not a categorical breakdown, even
    # though it contains the word "by".
    grain_phrase = bool(re.search(r"\b(?:by|per)\s+(?:day|week|month|quarter|year)\b", q))
    if time_intent and time_col and (dim is None or grain_phrase) and (not _explicit_group(q) or grain_phrase):
        measure_expr = _agg_expr(agg, measure)
        label_expr = f"date_trunc('{grain}', {quote_ident(time_col)})"
        sql = (
            f"SELECT {label_expr} AS label, {measure_expr} AS value FROM {t}{where_sql} "
            f"GROUP BY label ORDER BY label ASC"
        )
        return _answer(
            sql, "line", label_expr,
            f"{pretty(measure['name']) if measure else 'Records'} over time",
            f"Aggregated by {grain} ({agg}) across {pretty(time_col)}.",
            0.85, "trend", question,
            value_format=measure["semantic"] if measure else "number",
            x_label=pretty(time_col), y_label=pretty(measure["name"]) if measure else "Records",
            grain=grain,
        )

    # ---- grouped aggregate ----------------------------------------------
    if dim:
        dim_expr = _dim_expr(dim)
        if agg == "count" or not measure:
            value_expr = "COUNT(*)"
            fmt = "number"
            measure_label = "Records"
        else:
            value_expr = _agg_expr(agg, measure)
            fmt = measure["semantic"]
            measure_label = pretty(measure["name"])
        if share and measure:
            value_expr = (
                f"ROUND(100.0 * {_agg_expr(agg, measure)} / "
                f"NULLIF(SUM({_agg_expr(agg, measure)}) OVER (), 0), 2)"
            )
            fmt = "percent_points"
            measure_label = f"Share of {pretty(measure['name']).lower()}"
        sql = (
            f"SELECT {dim_expr} AS label, {value_expr} AS value FROM {t}{where_sql} "
            f"GROUP BY label ORDER BY value {order_dir}"
        )
        if top_n:
            sql += f" LIMIT {int(top_n)}"
        return _answer(
            sql, "bar", dim_expr,
            f"{measure_label} by {pretty(dim['name']).lower()}",
            f"Grouped by {pretty(dim['name']).lower()} and computed {agg}{' share' if share else ''}.",
            0.9 if not _is_fuzzy(q, dim) else 0.65,
            "share" if share else "group_by", question,
            value_format=fmt, x_label=pretty(dim["name"]), y_label=measure_label,
        )

    # ---- ranked time periods --------------------------------------------
    period = re.search(r"\b(?:which|what)\s+(day|week|month|quarter|year)\b", q)
    if period and time_col and measure and re.search(r"\b(highest|lowest|most|least|peak|worst|best)\b", q):
        unit = period.group(1)
        rank_agg = "sum" if measure["semantic"] in {"currency", "count"} else "avg"
        label_expr = f"date_trunc('{unit}', {quote_ident(time_col)})"
        sql = (
            f"SELECT {label_expr} AS label, {_agg_expr(rank_agg, measure)} AS value "
            f"FROM {t}{where_sql} GROUP BY label ORDER BY value {order_dir}"
        )
        return _answer(
            sql, "bar", label_expr,
            f"{pretty(measure['name'])} by {unit}",
            f"Ranked {unit}s by {rank_agg} of {pretty(measure['name'])}.",
            0.86, "time_rank", question,
            value_format=measure["semantic"],
            x_label=pretty(time_col), y_label=pretty(measure["name"]),
            grain=unit,
        )

    # ---- scalar ----------------------------------------------------------
    if measure:
        value_expr = _agg_expr("count" if agg == "count" else agg, measure)
        sql = f"SELECT {value_expr} AS value FROM {t}{where_sql}"
        label = pretty(measure["name"])
        prefix = {"sum": "Total", "avg": "Average", "median": "Median", "max": "Highest", "min": "Lowest", "count": "Count of"}.get(agg, "Total")
        title = f"{prefix} {label}"
        return _answer(
            sql, "kpi", None, title,
            f"Computed {agg} of {pretty(measure['name'])}.{' With filters.' if where else ''}",
            0.8, "scalar", question,
            value_format=measure["semantic"], x_label=title, y_label=label,
        )

    return None


# --------------------------------------------------------------------------- #
# Clause builders
# --------------------------------------------------------------------------- #
def _agg_expr(agg: str, measure: dict | None) -> str:
    if agg == "count" or not measure:
        return "COUNT(*)"
    column = quote_ident(measure["name"])
    if agg == "sum":
        return f"SUM({column})"
    if agg == "avg":
        return f"AVG({column})"
    if agg == "max":
        return f"MAX({column})"
    if agg == "min":
        return f"MIN({column})"
    if agg == "median":
        return f"MEDIAN({column})"
    return f"SUM({column})"


def _aggregation(q: str, measure: dict | None, time_intent: bool, has_dim: bool = False) -> str:
    if re.search(r"\b(average|avg|mean|typical)\b", q) and measure:
        return "avg"
    if re.search(r"\bmedian\b", q) and measure:
        return "median"
    if re.search(r"\b(total|sum|combined|aggregate)\b", q):
        return "sum"
    if re.search(r"\b(maximum|minimum)\b", q):
        return "max" if re.search(r"\bmaximum\b", q) else "min"
    if re.search(r"\b(how many|number of|count)\b", q) or not measure:
        return "count"
    semantic = measure["semantic"]
    default = "avg" if semantic in {"percentage", "number", "ordinal"} else "sum"
    if has_dim:
        return default
    if re.search(r"\b(highest|largest|most|peak)\b", q):
        return "max"
    if re.search(r"\b(lowest|smallest|least|worst)\b", q):
        return "min"
    return default


def _explicit_group(q: str) -> bool:
    return bool(re.search(
        r"\b(by|per|across|for each|within|grouped by|compare|versus|vs|which|top|bottom|breakdown|split)\b",
        q,
    ))


def _dim_expr(dim: dict) -> str:
    col = quote_ident(dim["name"])
    if dim["semantic"] == "boolean":
        return f"CASE WHEN {col} THEN 'Yes' ELSE 'No' END"
    if dim["semantic"] in {"category", "country"} and dim.get("distinct", 99) <= 20:
        canonical: dict[str, str] = {}
        for entry in dim.get("top_values") or []:
            raw = str(entry.get("value", "")).strip()
            if raw:
                canonical.setdefault(raw.lower(), raw)
        if len(canonical) >= 2:
            cases = " ".join(
                f"WHEN {quote_literal(key)} THEN {quote_literal(value)}"
                for key, value in canonical.items()
            )
            return (
                f"CASE LOWER(TRIM(CAST({col} AS VARCHAR))) {cases} "
                f"ELSE TRIM(CAST({col} AS VARCHAR)) END"
            )
    return f"TRIM(CAST({col} AS VARCHAR))"


def _value_clause(column: str, values: list[str]) -> str:
    parts = [f"LOWER(TRIM(CAST({quote_ident(column)} AS VARCHAR))) = {quote_literal(v.strip().lower())}" for v in values]
    return "(" + " OR ".join(parts) + ")"


def _exclusion_clause(column: str, values: list[str]) -> str:
    parts = [
        f"LOWER(TRIM(CAST({quote_ident(column)} AS VARCHAR))) <> {quote_literal(v.strip().lower())}"
        for v in values
    ]
    return "(" + " AND ".join(parts) + ")"


_EXCLUSION_CUE = re.compile(
    r"\b(?:excluding|except(?:\s+for)?|not|without|other\s+than|ignore|drop|minus|omit)\b"
)


def _exclusion_filters(q: str, dims: list[dict]) -> dict[str, list[str]]:
    """Values the question explicitly excludes.

    Only values from low-cardinality dimensions are considered, and the cue
    must sit immediately before the value ("not EMEA", "excluding Enterprise").
    That keeps "why is revenue not growing" from turning into a filter.
    """
    out: dict[str, list[str]] = {}
    for dim in dims:
        if dim.get("distinct", 0) > 20:
            continue
        hits: list[str] = []
        for entry in (dim.get("top_values") or [])[:20]:
            raw = str(entry.get("value", "")).strip()
            low = raw.lower()
            if len(low) < 3 or low in {"true", "false", "yes", "no", "none", "null"}:
                continue
            if any(low == h.lower() for h in hits):
                continue
            for match in re.finditer(rf"\b{re.escape(low)}\b", q):
                before = q[max(0, match.start() - 28):match.start()]
                after = q[match.end():match.end() + 24]
                if _EXCLUSION_CUE.search(before) or re.search(r"\b(?:excluded|omitted)\b", after):
                    hits.append(raw)
                    break
        if hits:
            out[dim["name"]] = hits
    return out


def _comparison_intent(q: str) -> tuple[str, int, bool] | None:
    if re.search(r"\b(?:year[\s-]*over[\s-]*year|yoy)\b", q):
        grain = "month" if re.search(r"\b(?:month|monthly|by month)\b", q) else "year"
        return grain, 12 if grain == "month" else 1, True
    if re.search(r"\b(?:quarter[\s-]*over[\s-]*quarter|qoq)\b", q):
        return "quarter", 1, False
    if re.search(r"\b(?:month[\s-]*over[\s-]*month|mom)\b", q):
        return "month", 1, False
    if re.search(r"\b(?:week[\s-]*over[\s-]*week|wow)\b", q):
        return "week", 1, False
    return None


def _numeric_filters(q: str, measures: list[dict]) -> list[str]:
    out: list[str] = []
    pattern = re.compile(
        r"\b([a-z][a-z0-9_ ]{1,30}?)\s*(>=|<=|>|<|above|below|over|under|at least|more than|less than)\s*\$?([\d][\d,]*(?:\.\d+)?)",
        re.I,
    )
    for match in pattern.finditer(q):
        phrase, op, number = match.group(1), match.group(2).lower(), match.group(3)
        column = _best_column(phrase, measures, threshold=0.7)
        if not column:
            continue
        sql_op = {
            "above": ">", "over": ">", "more than": ">", "at least": ">=",
            "below": "<", "under": "<", "less than": "<",
        }.get(op, op)
        try:
            value = float(number.replace(",", ""))
        except ValueError:
            continue
        out.append(f"CAST({quote_ident(column['name'])} AS DOUBLE) {sql_op} {value}")
    return out


def _time_filters(q: str, time_col: str | None, table: str) -> list[str]:
    if not time_col:
        return []
    col = quote_ident(time_col)
    anchor = f"date_trunc('{{unit}}', (SELECT MAX({col}) FROM {table}))"
    filters: list[str] = []
    used_rolling = False

    # "year to date", "month to date", "quarter to date".
    to_date = re.search(r"\b(year|month|quarter)\s*(?:-|\s)?to\s*date\b|\b(ytd|mtd|qtd)\b", q)
    if to_date:
        unit = to_date.group(1) or {"ytd": "year", "mtd": "month", "qtd": "quarter"}[to_date.group(2)]
        filters.append(f"{col} >= " + anchor.format(unit=unit))
        used_rolling = True

    # "last 6 months", "past 3 quarters", "rolling 4 weeks".
    rolling = re.search(
        r"\b(?:last|past|previous|trailing|rolling)\s+(?:(\d+)\s+)?(day|week|month|quarter|year)s?\b",
        q,
    )
    if rolling:
        count = max(1, int(rolling.group(1) or 1))
        unit = rolling.group(2)
        if count == 1:
            # "last month" means the previous complete calendar month, not the
            # current partial one, which would make a misleading total.
            start = anchor.format(unit=unit)
            filters.append(f"{col} >= {start} - INTERVAL '1 {unit}'")
            filters.append(f"{col} < {start}")
        else:
            filters.append(f"{col} >= " + anchor.format(unit=unit) + f" - INTERVAL '{count - 1} {unit}'")
        used_rolling = True

    this_period = re.search(r"\bthis\s+(day|week|month|quarter|year)\b", q)
    if this_period and not used_rolling:
        filters.append(f"{col} >= " + anchor.format(unit=this_period.group(1)))

    between = re.search(r"\bbetween\s+(20\d{2})\s+and\s+(20\d{2})\b", q)
    if between:
        filters.append(f"EXTRACT(YEAR FROM {col}) BETWEEN {int(between.group(1))} AND {int(between.group(2))}")
    year = re.search(r"\b(?:in|during|for)\s+(20\d{2})\b", q)
    if year and not between:
        filters.append(f"EXTRACT(YEAR FROM {col}) = {int(year.group(1))}")
    since = re.search(r"\bsince\s+(20\d{2})\b", q)
    if since:
        filters.append(f"EXTRACT(YEAR FROM {col}) >= {int(since.group(1))}")
    return filters


# --------------------------------------------------------------------------- #
# Column resolution
# --------------------------------------------------------------------------- #
def _best_column(text: str, columns: list[dict], threshold: float = 0.5) -> dict | None:
    if not columns:
        return None
    words = set(_tokens(text))
    text_norm = " " + " ".join(_tokens(text)) + " "
    best: tuple[float, dict] | None = None
    for col in columns:
        score = 0.0
        aliases = {
            col["name"].lower(),
            col["name"].replace("_", " ").lower(),
            pretty(col["name"]).lower(),
        }
        aliases.update(SYNONYMS.get(col["name"].lower(), []))
        aliases.update({a + "s" for a in list(aliases) if not a.endswith("s")})
        for alias in aliases:
            # "Over time" is a trend phrase, not a reference to an overtime column.
            if alias == "over time" and "overtime" not in words:
                continue
            alias_tokens = _tokens(alias)
            if not alias_tokens:
                continue
            if f" {' '.join(alias_tokens)} " in text_norm:
                score = max(score, 1.0)
                continue
            if all(tok in words for tok in alias_tokens):
                score = max(score, 0.88)
                continue
            if len(alias_tokens) == 1 and len(alias_tokens[0]) > 3:
                for word in words:
                    if len(word) > 3 and difflib.SequenceMatcher(None, alias_tokens[0], word).ratio() >= 0.86:
                        score = max(score, 0.62)
        if score >= threshold and (best is None or score > best[0]):
            best = (score, col)
    return best[1] if best else None


_TIME_GRAINS = {"day", "week", "month", "quarter", "year"}


def _unresolved_group(q: str, dims: list[dict], measures: list[dict]) -> bool:
    """True when the question asks to group by something absent from the schema.

    Answering "revenue by industry" with company-wide revenue would be
    confidently wrong, so the parser refuses instead.
    """
    phrase = re.search(r"\b(?:by|per|across|for each|within|grouped by)\s+([a-z0-9_ ]{2,40})", q)
    if phrase:
        target = re.split(r"\b(?:for|in|during|over|last|this|between|and|with|where|from)\b", phrase.group(1))[0].strip()
        if target and target not in _TIME_GRAINS:
            if _best_column(target, dims, threshold=0.45) is None and _best_column(target, measures, threshold=0.6) is None:
                return True
    top = re.search(r"\b(?:top|bottom|first|last)\s+\d+\s+([a-z][a-z0-9_]*)", q)
    if top and top.group(1).rstrip("s") not in _TIME_GRAINS:
        if _best_column(top.group(1), dims, threshold=0.5) is None:
            return True
    return False


def _multiple_group_request(q: str, dims: list[dict], time_col: str | None) -> bool:
    """True when the question asks for two breakdowns at once."""
    phrase = re.search(r"\b(?:by|per|across|for each|within|grouped by)\s+([a-z0-9_ ,]{2,60})", q)
    if not phrase:
        return False
    target = re.split(
        r"\b(?:for|in|during|over|last|this|between|with|where|from)\b",
        phrase.group(1),
    )[0]
    parts = [p.strip() for p in re.split(r"\s*(?:,|and)\s*", target) if p.strip()]
    found_dims = sum(1 for p in parts if _best_column(p, dims, threshold=0.5))
    found_time = sum(1 for p in parts if p in _TIME_GRAINS)
    return found_dims >= 2 or (found_dims >= 1 and found_time >= 1)


def _dimension_for_question(q: str, dims: list[dict]) -> dict | None:
    phrase = re.search(r"\b(?:by|per|across|for each|within|grouped by)\s+([a-z0-9_ ]{2,40})", q)
    if phrase:
        found = _best_column(phrase.group(1), dims, threshold=0.5)
        if found:
            return found
    found = _best_column(q, dims, threshold=0.7)
    if found:
        return found
    # If a value is named ("EMEA vs APAC"), infer its column.
    for dim in dims:
        if dim.get("distinct", 0) <= 20:
            for value in dim.get("top_values", []):
                label = str(value.get("value", "")).strip().lower()
                if len(label) >= 3 and re.search(rf"\b{re.escape(label)}\b", q):
                    return dim
    return None


def _value_filters(q: str, dims: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for dim in dims:
        if dim.get("distinct", 0) > 20:
            continue
        hits: dict[str, str] = {}
        for entry in dim.get("top_values", [])[:20]:
            raw = str(entry.get("value", "")).strip()
            low = raw.lower()
            if len(low) < 3 or low in {"true", "false", "yes", "no", "none", "null"}:
                continue
            if low in hits:
                continue
            if re.search(rf"\b{re.escape(low)}\b", q):
                hits[low] = raw
        if hits:
            out[dim["name"]] = list(hits.values())
    # If two columns contain the same value (plan/segment = Enterprise), keep one.
    deduped: dict[str, list[str]] = {}
    seen: set[tuple[str, ...]] = set()
    for name, vals in out.items():
        key = tuple(sorted(v.lower() for v in vals))
        if key in seen:
            continue
        seen.add(key)
        deduped[name] = vals
    return deduped


def _two_measures(q: str, measures: list[dict]) -> tuple[dict, dict] | None:
    chunks = re.split(r"\band\b|\bvs\b|\bversus\b|\bwith\b", q)
    found: list[dict] = []
    for chunk in chunks:
        col = _best_column(chunk, measures, threshold=0.7)
        if col and all(col["name"] != f["name"] for f in found):
            found.append(col)
    return (found[0], found[1]) if len(found) >= 2 else None


def _time_intent(q: str) -> bool:
    return bool(re.search(
        r"\b(over time|trend|time series|monthly|weekly|daily|quarterly|yearly|"
        r"by month|by week|by day|by quarter|by year|over the (?:last|past))\b",
        q,
    ))


def _grain(q: str) -> str:
    if re.search(r"\b(daily|by day|per day)\b", q):
        return "day"
    if re.search(r"\b(weekly|by week|per week)\b", q):
        return "week"
    if re.search(r"\b(quarterly|by quarter|per quarter)\b", q):
        return "quarter"
    if re.search(r"\b(yearly|annual|by year|per year)\b", q):
        return "year"
    return "month"


def _top_n(q: str) -> int | None:
    match = re.search(r"\b(?:top|first|bottom|last)\s+(\d+)\b", q)
    if not match:
        return None
    return max(1, min(int(match.group(1)), 50))


def _is_fuzzy(q: str, col: dict) -> bool:
    tokens = _tokens(q)
    names = {col["name"].lower(), col["name"].replace("_", " ").lower(), pretty(col["name"]).lower()}
    return not any(all(t in tokens for t in n.split()) for n in names)


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", str(text).lower()) if t and t not in STOPWORDS]


def _normalize(question: str) -> str:
    q = str(question or "").lower()
    q = q.replace("what's", "what is").replace("how's", "how is")
    q = re.sub(r"\s+", " ", q).strip()
    q = q.rstrip("?.!")
    return q


def _answer(
    sql: str,
    chart_type: str,
    group_expr: str | None,
    title: str,
    rationale: str,
    confidence: float,
    intent: str,
    question: str,
    **extra,
) -> dict:
    validate_sql(sql)
    return {
        "sql": sql,
        "chart_type": chart_type,
        "group_expr": group_expr,
        "title": title,
        "rationale": rationale,
        "confidence": round(confidence, 2),
        "intent": intent,
        "question": question,
        **extra,
    }
