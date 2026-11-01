"""Deterministic NL→SQL benchmark.

Every case must parse, emit the expected shape, and execute against the demo
dataset. This is intentionally not an LLM benchmark: it is the baseline that
must stay correct with no model and no network.

    python benchmarks/run.py
    python benchmarks/run.py --verbose
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from atlas.core.ingest import read_upload  # noqa: E402
from atlas.core.nlsql import parse_question  # noqa: E402
from atlas.core.profile import build_profile  # noqa: E402

DATASET = ROOT / "datasets" / "saas_revenue.csv"
CASES = ROOT / "benchmarks" / "nlq_saas.json"
TABLE = "ds_saasrevenue"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="Print every failure detail.")
    args = parser.parse_args()

    frame, _ = read_upload(DATASET.name, DATASET.read_bytes())
    profile = build_profile(frame, "saas-revenue", "SaaS Revenue")
    connection = duckdb.connect(":memory:")
    connection.register(TABLE, frame)
    cases = json.loads(CASES.read_text(encoding="utf-8"))

    passed = 0
    failures: list[str] = []
    started = time.perf_counter()

    for index, case in enumerate(cases, 1):
        question = case["question"]
        parsed = parse_question(question, profile, TABLE)
        problems: list[str] = []

        if case.get("refused"):
            if parsed is not None:
                problems.append(f"expected refusal, got {parsed.get('intent')}")
        elif parsed is None:
            problems.append("expected a plan, got refusal")
        else:
            if "intent" in case and parsed.get("intent") != case["intent"]:
                problems.append(f"intent: expected {case['intent']!r}, got {parsed.get('intent')!r}")
            if "chart" in case and parsed.get("chart_type") != case["chart"]:
                problems.append(
                    f"chart: expected {case['chart']!r}, got {parsed.get('chart_type')!r}"
                )
            if "grain" in case and parsed.get("grain") != case["grain"]:
                problems.append(f"grain: expected {case['grain']!r}, got {parsed.get('grain')!r}")
            sql = (parsed.get("sql") or "").lower()
            for needle in case.get("sql_contains", []):
                if needle.lower() not in sql:
                    problems.append(f"SQL is missing {needle!r}")
            if not problems:
                try:
                    connection.execute(parsed["sql"]).fetchmany(10)
                except Exception as exc:  # noqa: BLE001 - benchmark reports any failure
                    problems.append(f"SQL failed: {exc}")

        if problems:
            failures.append(question)
            print(f"FAIL  {index:02d}  {question}")
            for problem in problems:
                print(f"        - {problem}")
        else:
            passed += 1
            if args.verbose:
                print(f"PASS  {index:02d}  {question}")

    elapsed = time.perf_counter() - started
    total = len(cases)
    print()
    print(f"NL->SQL benchmark: {passed}/{total} passed in {elapsed:.2f}s")
    if failures:
        print(f"Failures: {len(failures)}")
        return 1
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
