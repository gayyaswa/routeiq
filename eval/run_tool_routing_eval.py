"""Tool routing eval — verifies the agent calls the correct POI discovery tool.

Rule:
  activities non-empty  →  must call select_pois_for_day  (activity-matched + scenic fills)
  activities empty      →  must call find_city_pois        (scenic-only)

Usage:
    python3 eval/run_tool_routing_eval.py

8 queries (4 with activities, 4 without).
Estimated runtime: ~5–10 minutes.
All cities use the Bay Area KG master (no Overpass fetch).

Output:
    Prints a pass/fail routing table.
    Saves eval/results_tool_routing.md
"""
from __future__ import annotations
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

from routeiq.agent import build_day_trip_graph
from eval.tool_routing_queries import TOOL_ROUTING_QUERIES
from eval.evaluators import ActivityEvaluator


def _table_header() -> str:
    return (
        "| ID | City | Activities | Expected Tool | Actual Tool | Routing | Stops | Time |\n"
        "|----|------|------------|---------------|-------------|---------|-------|------|\n"
    )


def _table_row(row: dict) -> str:
    acts = ", ".join(row["activities"]) or "—"
    icon = "PASS" if row["routing_pass"] else "FAIL"
    return (
        f"| {row['id']} | {row['city']} | {acts} "
        f"| `{row['expected_tool']}` | `{row['actual_first_poi_tool']}` "
        f"| {icon} | {row['stop_count']} | {row['elapsed_s']}s |\n"
    )


def main() -> None:
    print("RouteIQ — Tool Routing Eval")
    print(f"8 queries · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    graph = build_day_trip_graph()
    evaluator = ActivityEvaluator(graph)

    rows: list[dict] = []
    for q in TOOL_ROUTING_QUERIES:
        acts = ", ".join(q["activities"]) or "none"
        print(f"\n  [{q['id']}] {q['city']} | activities={acts}")
        print(f"       expected: {q['expected_tool']}")

        draft, messages, elapsed = evaluator.run_plan(q)
        scored = evaluator.score(q, draft, messages, elapsed)
        rows.append(scored)

        icon = "PASS" if scored["routing_pass"] else "FAIL"
        print(
            f"       actual:   {scored['actual_first_poi_tool']}  →  {icon}  "
            f"stops={scored['stop_count']}  t={scored['elapsed_s']}s"
        )
        if not scored["routing_pass"]:
            print(
                f"       *** ROUTING FAILURE: expected {scored['expected_tool']} "
                f"but got {scored['actual_first_poi_tool']} ***"
            )

    # Summary
    total = len(rows)
    routing_pass = sum(1 for r in rows if r["routing_pass"])
    with_acts = [r for r in rows if r["activities"]]
    without_acts = [r for r in rows if not r["activities"]]

    print("\n" + "=" * 70)
    print("ROUTING SUMMARY")
    print("=" * 70)
    print(f"Overall routing pass rate:  {routing_pass}/{total}")
    print(
        f"With activities    (→ select_pois_for_day): "
        f"{sum(1 for r in with_acts if r['routing_pass'])}/{len(with_acts)}"
    )
    print(
        f"Without activities (→ find_city_pois):      "
        f"{sum(1 for r in without_acts if r['routing_pass'])}/{len(without_acts)}"
    )

    table = _table_header() + "".join(_table_row(r) for r in rows)
    print("\n" + table)

    # Save
    results_path = Path(__file__).parent / "results_tool_routing.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = (
        f"# RouteIQ Tool Routing Eval\n\n"
        f"*Generated {timestamp}*\n\n"
        f"**Rule:** activities non-empty → `select_pois_for_day`; "
        f"activities empty → `find_city_pois`\n\n"
        f"**Pass rate:** {routing_pass}/{total}\n\n"
        f"{table}\n"
    )
    results_path.write_text(content)
    print(f"Results saved to: {results_path}")

    if routing_pass < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
