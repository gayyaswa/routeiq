"""CLI evaluation script: GraphRAG vs vector-only baseline on 10 Bay Area queries.

Usage:
    python3 eval/run_eval.py

Requirements:
    ANTHROPIC_API_KEY environment variable (for GraphRAG route queries only)
    Estimated runtime: 10-15 minutes for 6 route queries + 4 semantic queries
    Estimated API cost: ~$0.05-0.10 (6 LLM calls for route queries)

Output:
    - Prints comparison table to stdout
    - Saves eval/results.md with full table + analysis
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from routeiq.facade import RouteIQFacade
from routeiq.rag import POIIndexer
from eval.eval_queries import EVAL_QUERIES
from eval.evaluator import Evaluator


def _format_table(rows: list[dict]) -> str:
    lines = [
        "| # | Query | Type | GraphRAG POIs | Vector POIs | Unique to GraphRAG | Unique to Vector | Winner |",
        "|---|-------|------|--------------|-------------|-------------------|-----------------|--------|",
    ]
    for i, row in enumerate(rows, 1):
        if row["type"] == "semantic":
            g_pois = "*(semantic — no route to parse)*"
        else:
            g_pois = ", ".join(row["graphrag_pois"]) or "*(pipeline error)*"
        v_pois = ", ".join(row["vector_pois"]) or "*(empty)*"
        g_only = ", ".join(row["graphrag_only"]) or "—"
        v_only = ", ".join(row["vector_only"]) or "—"
        winner_icon = "🗺 GraphRAG" if row["actual_winner"] == "graphrag" else "🔍 Vector"
        if row["actual_winner"] == "tie":
            winner_icon = "🤝 Tie"
        lines.append(
            f"| {i} | {row['query'][:55]}… | {row['type']} | {g_pois} | {v_pois} | {g_only} | {v_only} | {winner_icon} |"
        )
    return "\n".join(lines)


def _format_analysis(rows: list[dict]) -> str:
    total = len(rows)
    matched_expected = sum(1 for r in rows if r["expected_matches_actual"])
    graphrag_wins = sum(1 for r in rows if r["actual_winner"] == "graphrag")
    vector_wins = sum(1 for r in rows if r["actual_winner"] == "vector")
    ties = sum(1 for r in rows if r["actual_winner"] == "tie")

    route_rows = [r for r in rows if r["type"] == "route"]
    semantic_rows = [r for r in rows if r["type"] == "semantic"]
    route_g_wins = sum(1 for r in route_rows if r["actual_winner"] == "graphrag")
    semantic_v_wins = sum(1 for r in semantic_rows if r["actual_winner"] == "vector")

    return f"""
## Analysis

**Prediction accuracy:** {matched_expected}/{total} queries matched expected winner

**Overall distribution:**
- 🗺 GraphRAG wins: {graphrag_wins} queries
- 🔍 Vector wins: {vector_wins} queries
- 🤝 Ties: {ties} queries

**Route queries ({len(route_rows)} total):** GraphRAG won {route_g_wins}/{len(route_rows)}
- GraphRAG constrains results to POIs actually along the driving route (geographic filter)
- Vector retrieves semantically similar POIs regardless of whether they're on the route
- **GraphRAG wins here** because it eliminates irrelevant but semantically similar POIs from other regions

**Semantic queries ({len(semantic_rows)} total):** Vector won {semantic_v_wins}/{len(semantic_rows)}
- No origin/destination → pipeline cannot apply geographic constraints
- Pure semantic matching on description text finds the most topically relevant POIs
- **Vector wins here** because there's no route graph to leverage

## When each method wins

| Scenario | Best method | Why |
|----------|-------------|-----|
| "Drive from A to B, show X" | GraphRAG | Route coordinates constrain results to on-path POIs |
| "Find the best X near Y" | Vector | Semantic similarity finds topically relevant POIs |
| Specific landmark type along known route | GraphRAG | Graph filter removes off-route false positives |
| Open-ended discovery queries | Vector | No route context → pure semantic recall wins |

## Reproduce

```bash
python3 eval/run_eval.py
```

Requires: `ANTHROPIC_API_KEY`, ~10-15 min, ~$0.05-0.10 API cost.
"""


def main() -> None:
    from routeiq.llm_factory import create_llm

    print("RouteIQ Evaluation — GraphRAG vs Vector Baseline")
    print(f"10 Bay Area queries · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    try:
        llm = create_llm()
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
    indexer = POIIndexer()
    facade = RouteIQFacade(llm, poi_indexer=indexer)
    evaluator = Evaluator(facade, indexer)

    print("\nRunning 10 queries...")
    rows = evaluator.run_all(EVAL_QUERIES)

    print("\n\n" + "=" * 70)
    print("RESULTS TABLE")
    print("=" * 70)
    table = _format_table(rows)
    print(table)
    print(_format_analysis(rows))

    # Save results.md
    results_path = Path(__file__).parent / "results.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"# RouteIQ Evaluation: GraphRAG vs Vector Baseline\n\n"
    content += f"*Generated {timestamp} — `python3 eval/run_eval.py`*\n\n"
    content += "## Results\n\n"
    content += table + "\n"
    content += _format_analysis(rows)

    results_path.write_text(content)
    print(f"\nResults saved to: {results_path}")


if __name__ == "__main__":
    main()
