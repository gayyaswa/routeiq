"""CLI evaluation script: Week 3 Agent Eval — Day Trip Planner quality across 6 Bay Area queries.

Usage:
    python3 eval/run_agent_eval.py

Requirements:
    ANTHROPIC_API_KEY or NEBIUS_API_KEY environment variable
    Estimated runtime: 15-30 minutes (6 live agent runs including 1 refinement cycle)
    Estimated API cost: ~$0.20-0.40

Output:
    - Prints single-pass table, refinement table, and summary to stdout
    - Saves eval/results_week3.md
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from routeiq.agent import build_day_trip_graph
from eval.agent_eval_queries import AGENT_EVAL_QUERIES
from eval.agent_evaluator import AgentEvaluator


def _format_single_pass_table(rows: list[dict]) -> str:
    lines = [
        "| # | City | Preferences | Stop Count | Pref Match % | Faithful % | Plan Time | Tool Calls | Pass/Fail |",
        "|---|------|-------------|------------|--------------|------------|-----------|------------|-----------|",
    ]
    for row in rows:
        prefs = ", ".join(row["preferences"])
        pref_pct = f"{row['preference_match_rate']:.0%}"
        faith_pct = f"{row['faithfulness_rate']:.0%}"
        t = f"{row['planning_time_s']}s"
        pf = row["pass_fail"]
        err = f" *(error)*" if row.get("error") else ""
        lines.append(
            f"| {row['id']} | {row['city']} | {prefs} | {row['stop_count']}{err} "
            f"| {pref_pct} | {faith_pct} | {t} | {row['tool_call_count']} | {pf} |"
        )
    return "\n".join(lines)


def _format_refinement_table(r: dict) -> str:
    if r is None:
        return "*No refinement result.*"

    delta_pct = f"{r['delta_rate']:.0%}"
    lines = [
        "| Phase | Stops | Beach stops | Museum stops | Delta % |",
        "|-------|-------|-------------|--------------|---------|",
        f"| Before | {r['before_stop_count']} | {r['before_beach_count']} | {r['before_museum_count']} | — |",
        f"| After  | {r['after_stop_count']} | {r['after_beach_count']} | {r['after_museum_count']} | {delta_pct} |",
    ]
    lines.append("")
    lines.append(f"**Refinement verdict: {r['verdict']}**")
    gained = "yes" if r["preference_gained"] else "no"
    lost = "yes" if r["preference_lost"] else "no"
    lines.append(f"- Beach preference gained: {gained}")
    lines.append(f"- Museum preference reduced: {lost}")
    return "\n".join(lines)


def _format_summary(rows: list[dict], refinement: dict | None) -> str:
    valid = [r for r in rows if not r.get("error")]
    total = len(rows)
    passes = sum(1 for r in rows if r["pass_fail"] == "PASS")

    avg_pref = sum(r["preference_match_rate"] for r in valid) / len(valid) if valid else 0.0
    avg_faith = sum(r["faithfulness_rate"] for r in valid) / len(valid) if valid else 0.0
    avg_time = sum(r["planning_time_s"] for r in rows) / total if rows else 0.0
    avg_tools = sum(r["tool_call_count"] for r in rows) / total if rows else 0.0

    lines = [
        "## Summary",
        "",
        f"**Queries run:** {total}  ",
        f"**Pass/Fail:** {passes}/{total}  ",
        f"**Avg preference match:** {avg_pref:.0%}  ",
        f"**Avg faithfulness:** {avg_faith:.0%}  ",
        f"**Avg plan time:** {avg_time:.1f}s  ",
        f"**Avg tool calls:** {avg_tools:.1f}  ",
    ]

    if refinement:
        lines.append(f"**Refinement delta:** {refinement['delta_rate']:.0%}  ")
        lines.append(f"**Refinement verdict:** {refinement['verdict']}  ")

    return "\n".join(lines)


def main() -> None:
    print("RouteIQ — Week 3 Agent Eval (Day Trip Planner)")
    print(f"6 Bay Area queries · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    graph = build_day_trip_graph()
    evaluator = AgentEvaluator(graph)

    print("\nRunning 6 queries (5 single-pass + 1 refinement)...")
    rows, refinement = evaluator.run_all(AGENT_EVAL_QUERIES)

    print("\n\n" + "=" * 70)
    print("SECTION 1: Single-Pass Results")
    print("=" * 70)
    single_table = _format_single_pass_table(rows)
    print(single_table)

    print("\n" + "=" * 70)
    print("SECTION 2: Refinement Results (Query 6)")
    print("=" * 70)
    refine_table = _format_refinement_table(refinement)
    print(refine_table)

    print("\n" + "=" * 70)
    print("SECTION 3: Summary")
    print("=" * 70)
    summary = _format_summary(rows, refinement)
    print(summary)

    results_path = Path(__file__).parent / "results_week3.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = "# RouteIQ Week 3 Agent Eval — Day Trip Planner\n\n"
    content += f"*Generated {timestamp} — `python3 eval/run_agent_eval.py`*\n\n"
    content += "## Section 1: Single-Pass Results\n\n"
    content += single_table + "\n\n"
    content += "## Section 2: Refinement Results (Query 6)\n\n"
    content += refine_table + "\n\n"
    content += summary + "\n"

    results_path.write_text(content)
    print(f"\nResults saved to: {results_path}")


if __name__ == "__main__":
    main()
