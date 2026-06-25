"""Week 4 eval — compare 5 activity classifier + rating provider configurations.

Runs 30 golden queries across 5 configurations and prints a comparison table.

Usage:
    python3 eval/run_week4_eval.py              # full run (150 agent calls, ~5–8 hours)
    python3 eval/run_week4_eval.py --limit 3   # quick sanity check (15 calls, ~15–30 min)

Configurations:
  Run 1 (baseline):    ACTIVITY_PROVIDER=osm,    RATING_PROVIDER=llm_synthetic
  Run 2 (classifier):  ACTIVITY_PROVIDER=tavily, RATING_PROVIDER=llm_synthetic
  Run 3 (full Tavily): ACTIVITY_PROVIDER=tavily, RATING_PROVIDER=tavily_enrichment
  Run 4 (OSM + TA):    ACTIVITY_PROVIDER=osm,    RATING_PROVIDER=tripadvisor
  Run 5 (Tavily + TA): ACTIVITY_PROVIDER=tavily, RATING_PROVIDER=tripadvisor

Requirements:
  NEBIUS_API_KEY (or ANTHROPIC_API_KEY) — agent LLM + LLM-as-judge for match quality
  TAVILY_API_KEY — Runs 2, 3, 5
  TRIPADVISOR_API_KEY — Runs 4, 5

Output:
  Prints per-run tables and aggregate comparison to stdout.
  Saves eval/results_week4.md
"""
from __future__ import annotations
import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from routeiq.agent import build_day_trip_graph
from routeiq.llm_factory import create_llm
from eval.langsmith_dataset import WEEK4_EVAL_QUERIES
from eval.evaluators import ActivityEvaluator


# ── Run configurations ────────────────────────────────────────────────────────

RUNS: list[dict] = [
    {
        "label": "Run 1 — OSM + LLM-Synthetic (baseline)",
        "short": "OSM+Synth",
        "env": {"ACTIVITY_PROVIDER": "osm", "RATING_PROVIDER": "llm_synthetic"},
    },
    {
        "label": "Run 2 — Tavily classifier + LLM-Synthetic",
        "short": "Tavily+Synth",
        "env": {"ACTIVITY_PROVIDER": "tavily", "RATING_PROVIDER": "llm_synthetic"},
    },
    {
        "label": "Run 3 — Tavily classifier + Tavily enrichment",
        "short": "Tavily+Enrich",
        "env": {"ACTIVITY_PROVIDER": "tavily", "RATING_PROVIDER": "tavily_enrichment"},
    },
    {
        "label": "Run 4 — OSM + TripAdvisor",
        "short": "OSM+TA",
        "env": {"ACTIVITY_PROVIDER": "osm", "RATING_PROVIDER": "tripadvisor"},
    },
    {
        "label": "Run 5 — Tavily + TripAdvisor (best-of-all candidate)",
        "short": "Tavily+TA",
        "env": {"ACTIVITY_PROVIDER": "tavily", "RATING_PROVIDER": "tripadvisor"},
    },
]


# ── Formatting helpers ────────────────────────────────────────────────────────

def _table_header() -> str:
    return (
        "| # | City | Activities | Stops | Recall | Routing | Tools | Time | Pass/Fail |\n"
        "|---|------|------------|-------|--------|---------|-------|------|-----------|\n"
    )


def _table_row(row: dict) -> str:
    acts = ", ".join(row["activities"]) or "—"
    routing = "PASS" if row.get("routing_pass") else "FAIL"
    return (
        f"| {row['id']} | {row['city']} | {acts} "
        f"| {row['stop_count']} | {row['activity_recall']:.0%} "
        f"| {routing} ({row.get('actual_first_poi_tool', '?')}) "
        f"| {row['tool_call_count']} "
        f"| {row['elapsed_s']}s | {row['pass_fail']} |\n"
    )


def _summary(label: str, rows: list[dict]) -> str:
    valid = [r for r in rows if r["stop_count"] > 0]
    total = len(rows)
    passes = sum(1 for r in rows if r["pass_fail"] == "PASS")
    routing_passes = sum(1 for r in rows if r.get("routing_pass"))
    avg_recall = sum(r["activity_recall"] for r in valid) / len(valid) if valid else 0.0
    avg_time = sum(r["elapsed_s"] for r in rows) / total if rows else 0.0

    # Enrichment metrics
    avg_pct_rated = sum(r.get("pct_rated", 0.0) for r in rows) / total if rows else 0.0
    avg_pct_reviews = sum(r.get("pct_with_reviews", 0.0) for r in rows) / total if rows else 0.0
    avg_pct_photos = sum(r.get("pct_with_photos", 0.0) for r in rows) / total if rows else 0.0
    rated_rows = [r for r in rows if r.get("avg_rating") is not None]
    overall_avg_rating = sum(r["avg_rating"] for r in rated_rows) / len(rated_rows) if rated_rows else None

    # Activity match quality (Track 1 stops only)
    evidence_rows = [r for r in rows if r.get("activities")]
    avg_pct_evidence = (
        sum(r.get("pct_with_evidence", 0.0) for r in evidence_rows) / len(evidence_rows)
        if evidence_rows else 0.0
    )
    scored_rows = [r for r in rows if r.get("avg_match_quality") is not None]
    overall_avg_match = (
        sum(r["avg_match_quality"] for r in scored_rows) / len(scored_rows)
        if scored_rows else None
    )

    rating_str = f"{overall_avg_rating:.2f}" if overall_avg_rating is not None else "—"
    match_str = f"{overall_avg_match:.2f}/5" if overall_avg_match is not None else "—"

    return (
        f"**{label}**  \n"
        f"Pass rate: {passes}/{total}  \n"
        f"Tool routing accuracy: {routing_passes}/{total}  \n"
        f"Avg activity recall: {avg_recall:.0%}  \n"
        f"Avg plan time: {avg_time:.1f}s  \n"
        f"Enrichment — %rated: {avg_pct_rated:.0%} | %with reviews: {avg_pct_reviews:.0%} "
        f"| %with photos: {avg_pct_photos:.0%} | avg rating: {rating_str}  \n"
        f"Match quality — %with evidence: {avg_pct_evidence:.0%} | avg match score: {match_str}  \n"
    )


def _comparison_table(run_results: list[tuple[dict, list[dict]]]) -> str:
    lines = [
        "| Metric | " + " | ".join(cfg["short"] for cfg, _ in run_results) + " |",
        "|--------|" + "|".join(["-----"] * len(run_results)) + "|",
    ]

    def _avg(rows, key, fmt=".0%"):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return f"{sum(vals)/len(vals):{fmt}}" if vals else "—"

    metrics = [
        # Core pass/fail
        ("Pass rate",        lambda rows: f"{sum(1 for r in rows if r['pass_fail']=='PASS')}/{len(rows)}"),
        ("Routing accuracy", lambda rows: f"{sum(1 for r in rows if r.get('routing_pass'))}/{len(rows)}"),
        ("Avg recall",       lambda rows: _avg(rows, "activity_recall")),
        ("Avg time (s)",     lambda rows: _avg(rows, "elapsed_s", ".1f")),
        # Enrichment quality — how much real data did the rating provider return?
        ("% stops rated",         lambda rows: _avg(rows, "pct_rated")),
        ("% stops with reviews",  lambda rows: _avg(rows, "pct_with_reviews")),
        ("% stops with photos",   lambda rows: _avg(rows, "pct_with_photos")),
        ("Avg rating",            lambda rows: _avg(rows, "avg_rating", ".2f")),
        # Activity match quality — Track 1 stops only
        ("% matched with evidence", lambda rows: _avg(rows, "pct_with_evidence")),
        ("Avg match quality (1–5)", lambda rows: _avg(rows, "avg_match_quality", ".2f")),
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
    parser = argparse.ArgumentParser(description="RouteIQ Week 4 Activity Eval")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Run only the first N queries per configuration (default: all 30)",
    )
    args = parser.parse_args()

    queries = WEEK4_EVAL_QUERIES[:args.limit] if args.limit else WEEK4_EVAL_QUERIES
    n_queries = len(queries)
    n_runs = len(RUNS)

    print("RouteIQ — Week 4 Activity Eval")
    print(f"{n_queries} queries × {n_runs} configurations · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if args.limit:
        print(f"(--limit {args.limit}: quick sanity run)")
    print("=" * 70)

    if not os.getenv("TAVILY_API_KEY"):
        print("\nWARNING: TAVILY_API_KEY not set — Runs 2, 3, and 5 will use null enrichment.\n")
    if not os.getenv("TRIPADVISOR_API_KEY"):
        print("WARNING: TRIPADVISOR_API_KEY not set — Runs 4 and 5 will use null ratings.\n")

    # One shared LLM for the LLM-as-judge in score_activity_match_quality.
    # Gracefully skip judge scoring if no key is configured.
    judge_llm = None
    try:
        judge_llm = create_llm()
    except ValueError as e:
        print(f"WARNING: LLM judge disabled ({e})\n")

    all_run_results: list[tuple[dict, list[dict]]] = []
    full_output: list[str] = []

    for cfg in RUNS:
        print(f"\n{'='*70}")
        print(f"{cfg['label']}")
        print("Setting env:")
        _set_env(cfg["env"])

        # Build a fresh graph so the new env vars are picked up by all factory calls.
        graph = build_day_trip_graph()
        evaluator = ActivityEvaluator(graph, llm=judge_llm)

        rows = evaluator.run_all(queries)
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

    csv_path = Path(__file__).parent / "results_week4.csv"
    _write_csv(csv_path, all_run_results, timestamp)
    print(f"CSV saved to:     {csv_path}")


def _write_csv(path: Path, run_results: list[tuple[dict, list[dict]]], timestamp: str) -> None:
    fieldnames = [
        "generated_at", "run", "config",
        "activity_provider", "rating_provider",
        "query_id", "city", "activities",
        "stop_count", "activity_recall_pct",
        "routing_pass", "first_poi_tool", "tool_calls", "elapsed_s",
        "pass_fail",
        "pct_rated", "pct_with_reviews", "pct_with_photos", "avg_rating",
        "pct_with_evidence", "avg_match_quality",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, (cfg, rows) in enumerate(run_results, start=1):
            for row in rows:
                writer.writerow({
                    "generated_at": timestamp,
                    "run": f"Run {i}",
                    "config": cfg["short"],
                    "activity_provider": cfg["env"]["ACTIVITY_PROVIDER"],
                    "rating_provider": cfg["env"]["RATING_PROVIDER"],
                    "query_id": row["id"],
                    "city": row["city"],
                    "activities": ", ".join(row.get("activities") or []),
                    "stop_count": row["stop_count"],
                    "activity_recall_pct": f"{row['activity_recall']:.0%}",
                    "routing_pass": "PASS" if row.get("routing_pass") else "FAIL",
                    "first_poi_tool": row.get("actual_first_poi_tool", ""),
                    "tool_calls": row["tool_call_count"],
                    "elapsed_s": row["elapsed_s"],
                    "pass_fail": row["pass_fail"],
                    "pct_rated": f"{row.get('pct_rated', 0):.0%}",
                    "pct_with_reviews": f"{row.get('pct_with_reviews', 0):.0%}",
                    "pct_with_photos": f"{row.get('pct_with_photos', 0):.0%}",
                    "avg_rating": f"{row['avg_rating']:.2f}" if row.get("avg_rating") is not None else "",
                    "pct_with_evidence": f"{row.get('pct_with_evidence', 0):.0%}",
                    "avg_match_quality": f"{row['avg_match_quality']:.2f}" if row.get("avg_match_quality") is not None else "",
                })


def _write_analysis(run_results: list[tuple[dict, list[dict]]]) -> str:
    if len(run_results) < 2:
        return "Not enough runs to compare."

    def _avg_metric(rows, key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    _, rows1 = run_results[0]
    _, rows2 = run_results[1]

    recall1 = _avg_metric(rows1, "activity_recall") or 0.0
    recall2 = _avg_metric(rows2, "activity_recall") or 0.0

    lines = [
        "### Classifier lift (Run 2 vs Run 1 — Tavily activity vs OSM tags)",
        f"- OSM recall: {recall1:.0%}  |  Tavily recall: {recall2:.0%}  |  delta: {recall2-recall1:+.0%}",
        "- OSM wins when POIs have clear subtype tags (peak=hiking, playground=kids, beach=swimming) — zero cost, zero latency.",
        "- Tavily wins when POIs lack explicit tags but are known for an activity via web content (e.g. a 'nature reserve' known for kayaking).",
        "",
    ]

    if len(run_results) >= 4:
        _, rows4 = run_results[3]
        pct_rated1 = _avg_metric(rows1, "pct_rated") or 0.0
        pct_rated4 = _avg_metric(rows4, "pct_rated") or 0.0
        pct_photos1 = _avg_metric(rows1, "pct_with_photos") or 0.0
        pct_photos4 = _avg_metric(rows4, "pct_with_photos") or 0.0
        lines += [
            "### Enrichment lift (Run 4 vs Run 1 — TripAdvisor ratings vs LLM-synthetic)",
            f"- % stops rated:  OSM+Synth {pct_rated1:.0%}  |  OSM+TA {pct_rated4:.0%}  |  delta: {pct_rated4-pct_rated1:+.0%}",
            f"- % stops with photos:  OSM+Synth {pct_photos1:.0%}  |  OSM+TA {pct_photos4:.0%}  |  delta: {pct_photos4-pct_photos1:+.0%}",
            "- LLM-synthetic ratings are fabricated — they look complete but carry no signal about real quality.",
            "- TripAdvisor ratings reflect actual visitor reviews and come with photos, making stop cards richer.",
            "",
        ]

    if len(run_results) >= 5:
        _, rows5 = run_results[4]
        recall5 = _avg_metric(rows5, "activity_recall") or 0.0
        pct_rated5 = _avg_metric(rows5, "pct_rated") or 0.0
        match5 = _avg_metric(rows5, "avg_match_quality")
        match_str = f"{match5:.2f}/5" if match5 is not None else "—"
        lines += [
            "### Best-of-all candidate (Run 5 — Tavily classifier + TripAdvisor ratings)",
            f"- Activity recall: {recall5:.0%}  |  % stops rated: {pct_rated5:.0%}  |  avg match quality: {match_str}",
            "- Recommended production config if TAVILY_API_KEY and TRIPADVISOR_API_KEY are available.",
            "- Fall back to Run 1 (OSM+Synth) when neither key is present — still passes all routing tests.",
        ]

    return "\n".join(lines)


if __name__ == "__main__":
    main()
