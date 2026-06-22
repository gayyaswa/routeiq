"""Week 4 eval — compare 3 activity classifier + rating provider configurations.

Runs 30 golden queries across 3 configurations and prints a comparison table.

Usage:
    python3 eval/run_week4_eval.py

Configurations:
  Run 1 (baseline):       ACTIVITY_PROVIDER=osm,    RATING_PROVIDER=llm_synthetic
  Run 2 (classifier lift):ACTIVITY_PROVIDER=tavily, RATING_PROVIDER=llm_synthetic
  Run 3 (full Tavily):    ACTIVITY_PROVIDER=tavily, RATING_PROVIDER=tavily_enrich

Requirements:
  NEBIUS_API_KEY (or ANTHROPIC_API_KEY) for LLM calls
  TAVILY_API_KEY for Runs 2 and 3
  Estimated runtime: 3–5 hours (90 live agent runs)
  Estimated cost: ~$1–3 depending on provider

Output:
  Prints per-run tables and aggregate comparison to stdout.
  Saves eval/results_week4.md
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
from eval.langsmith_dataset import WEEK4_EVAL_QUERIES
from eval.evaluators import ActivityEvaluator


# ── Run configurations ────────────────────────────────────────────────────────

RUNS: list[dict] = [
    {
        "label": "Run 1 — OSM + LLM-Synthetic (baseline)",
        "short": "OSM+Synth",
        "env": {
            "ACTIVITY_PROVIDER": "osm",
            "RATING_PROVIDER": "llm_synthetic",
        },
    },
    {
        "label": "Run 2 — Tavily classifier + LLM-Synthetic",
        "short": "Tavily+Synth",
        "env": {
            "ACTIVITY_PROVIDER": "tavily",
            "RATING_PROVIDER": "llm_synthetic",
        },
    },
    {
        "label": "Run 3 — Tavily classifier + Tavily enrichment",
        "short": "Tavily+Enrich",
        "env": {
            "ACTIVITY_PROVIDER": "tavily",
            "RATING_PROVIDER": "tavily_enrichment",
        },
    },
]


# ── Formatting helpers ────────────────────────────────────────────────────────

def _table_header() -> str:
    return (
        "| # | City | Activities | Stops | Recall | Coverage | Tools | Time | Pass/Fail |\n"
        "|---|------|------------|-------|--------|----------|-------|------|-----------|\n"
    )


def _table_row(row: dict) -> str:
    acts = ", ".join(row["activities"]) or "—"
    return (
        f"| {row['id']} | {row['city']} | {acts} "
        f"| {row['stop_count']} | {row['activity_recall']:.0%} "
        f"| {row['activity_coverage']:.0%} | {row['tool_call_count']} "
        f"| {row['elapsed_s']}s | {row['pass_fail']} |\n"
    )


def _summary(label: str, rows: list[dict]) -> str:
    valid = [r for r in rows if r["stop_count"] > 0]
    total = len(rows)
    passes = sum(1 for r in rows if r["pass_fail"] == "PASS")
    avg_recall = sum(r["activity_recall"] for r in valid) / len(valid) if valid else 0.0
    avg_coverage = sum(r["activity_coverage"] for r in valid) / len(valid) if valid else 0.0
    avg_time = sum(r["elapsed_s"] for r in rows) / total if rows else 0.0

    return (
        f"**{label}**  \n"
        f"Pass rate: {passes}/{total}  \n"
        f"Avg activity recall: {avg_recall:.0%}  \n"
        f"Avg activity coverage: {avg_coverage:.0%}  \n"
        f"Avg plan time: {avg_time:.1f}s  \n"
    )


def _comparison_table(run_results: list[tuple[dict, list[dict]]]) -> str:
    lines = [
        "| Metric | " + " | ".join(cfg["short"] for cfg, _ in run_results) + " |",
        "|--------|" + "|".join(["-----"] * len(run_results)) + "|",
    ]
    metrics = [
        ("Pass rate", lambda rows: f"{sum(1 for r in rows if r['pass_fail']=='PASS')}/{len(rows)}"),
        ("Avg recall", lambda rows: f"{sum(r['activity_recall'] for r in rows)/len(rows):.0%}" if rows else "—"),
        ("Avg coverage", lambda rows: f"{sum(r['activity_coverage'] for r in rows)/len(rows):.0%}" if rows else "—"),
        ("Avg time (s)", lambda rows: f"{sum(r['elapsed_s'] for r in rows)/len(rows):.1f}" if rows else "—"),
    ]
    for label, fn in metrics:
        values = [fn(rows) for _, rows in run_results]
        lines.append(f"| {label} | " + " | ".join(values) + " |")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def _set_env(env: dict[str, str]) -> None:
    for k, v in env.items():
        os.environ[k] = v
        print(f"  {k}={v}")


def main() -> None:
    print("RouteIQ — Week 4 Activity Eval")
    print(f"30 queries × 3 configurations · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if not tavily_key:
        print("\nWARNING: TAVILY_API_KEY not set — Runs 2 and 3 will use null enrichment.\n")

    all_run_results: list[tuple[dict, list[dict]]] = []
    full_output: list[str] = []

    for cfg in RUNS:
        print(f"\n{'='*70}")
        print(f"{cfg['label']}")
        print("Setting env:")
        _set_env(cfg["env"])

        # Build a fresh graph so the new env vars are picked up by all factory calls.
        graph = build_day_trip_graph()
        evaluator = ActivityEvaluator(graph)

        rows = evaluator.run_all(WEEK4_EVAL_QUERIES)
        all_run_results.append((cfg, rows))

        # Print section
        print(f"\n--- {cfg['label']} ---")
        table = _table_header() + "".join(_table_row(r) for r in rows)
        print(table)
        summ = _summary(cfg["label"], rows)
        print(summ)

        full_output.append(f"## {cfg['label']}\n\n{table}\n{summ}\n")

    # Comparison table
    print("\n" + "=" * 70)
    print("COMPARISON ACROSS RUNS")
    print("=" * 70)
    comparison = _comparison_table(all_run_results)
    print(comparison)
    full_output.append(f"## Comparison Across Runs\n\n{comparison}\n")

    # Analysis notes
    analysis = _write_analysis(all_run_results)
    print("\n" + analysis)
    full_output.append(f"## Analysis\n\n{analysis}\n")

    # Save results
    results_path = Path(__file__).parent / "results_week4.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"# RouteIQ Week 4 Activity Eval\n\n*Generated {timestamp}*\n\n"
    content += "\n".join(full_output)
    results_path.write_text(content)
    print(f"\nResults saved to: {results_path}")


def _write_analysis(run_results: list[tuple[dict, list[dict]]]) -> str:
    if len(run_results) < 2:
        return "Not enough runs to compare."

    _, rows1 = run_results[0]
    _, rows2 = run_results[1]

    recall1 = sum(r["activity_recall"] for r in rows1) / len(rows1) if rows1 else 0.0
    recall2 = sum(r["activity_recall"] for r in rows2) / len(rows2) if rows2 else 0.0
    lift = recall2 - recall1

    lines = [
        "### Classifier lift (Run 2 vs Run 1)",
        f"- Tavily recall advantage: {lift:+.0%}",
        f"- OSM recall: {recall1:.0%}  |  Tavily recall: {recall2:.0%}",
        "",
        "### When OSM wins",
        "- POIs with clear OSM tags (peak=hiking, playground=kids, beach=swimming)",
        "- Zero API cost, zero latency",
        "",
        "### When Tavily wins",
        "- POIs without explicit OSM subtype tags",
        "- Activities inferred from web content (e.g. a 'nature reserve' known for kayaking)",
        "",
    ]
    if len(run_results) >= 3:
        _, rows3 = run_results[2]
        coverage3 = sum(r["activity_coverage"] for r in rows3) / len(rows3) if rows3 else 0.0
        coverage2 = sum(r["activity_coverage"] for r in rows2) / len(rows2) if rows2 else 0.0
        lines += [
            "### Enrichment lift (Run 3 vs Run 2)",
            f"- Coverage with Tavily enrichment: {coverage3:.0%}  |  without: {coverage2:.0%}",
        ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
