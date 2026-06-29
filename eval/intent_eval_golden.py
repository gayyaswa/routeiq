"""Intent classifier golden eval — 21 queries across 3 tiers.

Measures keyword-bag baseline vs fine-tuned QueryIntentClassifier.
The key submission metric is Tier 2 delta: baseline ≈ 0%, fine-tuned ≥ 80%.

Usage:
    python3 eval/intent_eval_golden.py --baseline          # keyword bag only
    python3 eval/intent_eval_golden.py --finetuned         # fine-tuned model only
    python3 eval/intent_eval_golden.py                     # both (comparison)

    FINETUNED_MODEL_PATH=./models/intent python3 eval/intent_eval_golden.py
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# ── Golden query set ────────────────────────────────────────────────────────

GOLDEN_QUERIES: list[dict] = [
    # Tier 1 — Easy: keyword bag should handle these
    {"tier": 1, "query": "I want to go hiking near the city",        "expected": ["hiking"]},
    {"tier": 1, "query": "planning a family picnic in the park",     "expected": ["picnic", "kids"]},
    {"tier": 1, "query": "find a good swimming beach",               "expected": ["swimming"]},
    {"tier": 1, "query": "bike trail along the coast",               "expected": ["biking"]},
    {"tier": 1, "query": "kayaking on the bay",                      "expected": ["kayaking"]},

    # Tier 2 — Semantic gap: keyword bag fails, fine-tuned should pass
    {"tier": 2, "query": "somewhere with a waterfall",               "expected": ["hiking"]},
    {"tier": 2, "query": "my 6-year-old would love it",             "expected": ["kids"]},
    {"tier": 2, "query": "rollercoasters and theme parks",           "expected": ["kids"]},
    {"tier": 2, "query": "wine country tour",                        "expected": ["food"]},
    {"tier": 2, "query": "historic old town and missions",           "expected": ["history"]},
    {"tier": 2, "query": "somewhere with great ocean views",         "expected": ["scenic"]},
    {"tier": 2, "query": "paddleboard or snorkel spot",              "expected": ["kayaking", "swimming"]},
    {"tier": 2, "query": "bouldering spot near the city",            "expected": ["hiking"]},
    {"tier": 2, "query": "little ones need entertainment",           "expected": ["kids"]},
    {"tier": 2, "query": "brewery and food market district",         "expected": ["food"]},

    # Tier 3 — Multi-label: upper bound, both may struggle
    {"tier": 3, "query": "scenic coastal hike with the kids",        "expected": ["hiking", "kids"]},
    {"tier": 3, "query": "wine tasting and a nice nature walk",      "expected": ["food", "hiking"]},
    {"tier": 3, "query": "historic brewery district tour",           "expected": ["history", "food"]},
    {"tier": 3, "query": "beach day with the family",               "expected": ["swimming", "kids"]},
    {"tier": 3, "query": "show me a nice day in SF",                "expected": []},
    {"tier": 3, "query": "plan a relaxing afternoon",               "expected": []},
]

# Keyword bag — mirrors _infer_activities_from_text in app.py
_KEYWORD_MAP: dict[str, list[str]] = {
    "hiking":    ["hik", "trail", "trek", "nature walk", "nature reserve"],
    "biking":    ["bik", "cycling", "cycle", "mountain bik"],
    "swimming":  ["swim", "beach", "pool", "snorkel"],
    "kayaking":  ["kayak", "paddleboard", "canoe", "water sport"],
    "kids":      ["kid", "child", "children", "family", "playground", "zoo"],
    "picnic":    ["picnic", "garden", "park"],
    "history":   ["histor", "museum", "mission", "battlefield", "heritage"],
    "food":      ["winer", "winery", "brewery", "food market", "farm stand", "tasting room"],
    "scenic":    ["scenic", "overlook", "viewpoint", "vista", "coastal view"],
}


@dataclass
class EvalResult:
    tier: int
    query: str
    expected: list[str]
    predicted: list[str]

    @property
    def is_hit(self) -> bool:
        """All expected tags in predicted, no extra wrong tags (unless expected is empty)."""
        if not self.expected:
            return len(self.predicted) == 0
        return all(t in self.predicted for t in self.expected) and all(
            t in self.expected for t in self.predicted
        )

    @property
    def is_partial(self) -> bool:
        if not self.expected:
            return False
        return any(t in self.predicted for t in self.expected)

    @property
    def is_miss(self) -> bool:
        if not self.expected:
            return len(self.predicted) > 0
        return len(self.predicted) == 0 or not any(t in self.predicted for t in self.expected)


# ── Classifiers ─────────────────────────────────────────────────────────────

def _keyword_bag_classify(text: str) -> list[str]:
    """Keyword bag baseline — mirrors _infer_activities_from_text in app.py."""
    text_lower = text.lower()
    return [tag for tag, kws in _KEYWORD_MAP.items() if any(kw in text_lower for kw in kws)]


_clf_instance = None  # module-level cache — loaded once per eval run


def _finetuned_classify(text: str, model_path: str) -> list[str]:
    """Fine-tuned QueryIntentClassifier — loaded once, reused for all queries."""
    global _clf_instance
    try:
        from routeiq.activities.finetuned_classifier import QueryIntentClassifier
        if _clf_instance is None:
            _clf_instance = QueryIntentClassifier(model_path=model_path)
        result = _clf_instance.classify(text)
        return result["activities"]
    except ImportError:
        raise RuntimeError(
            "routeiq/activities/finetuned_classifier.py not yet created. "
            "Run --baseline first, then build the classifier after training."
        )


# ── Eval runner ──────────────────────────────────────────────────────────────

def run_intent_eval(classifier_fn, label: str) -> list[EvalResult]:
    results = []
    for q in GOLDEN_QUERIES:
        predicted = classifier_fn(q["query"])
        results.append(EvalResult(
            tier=q["tier"],
            query=q["query"],
            expected=q["expected"],
            predicted=predicted,
        ))
    return results


def _tier_accuracy(results: list[EvalResult], tier: int) -> tuple[int, int, int, int]:
    subset = [r for r in results if r.tier == tier]
    hits = sum(1 for r in subset if r.is_hit)
    partials = sum(1 for r in subset if not r.is_hit and r.is_partial)
    misses = sum(1 for r in subset if r.is_miss)
    return hits, partials, misses, len(subset)


def _log_results(label: str, results: list[EvalResult]) -> None:
    logger.info("\n%s", "=" * 60)
    logger.info("  %s", label)
    logger.info("%s", "=" * 60)

    tier_labels = {1: "Tier 1 — Easy", 2: "Tier 2 — Semantic gap", 3: "Tier 3 — Multi-label"}
    for tier in [1, 2, 3]:
        subset = [r for r in results if r.tier == tier]
        hits, partials, misses, total = _tier_accuracy(results, tier)
        logger.info("\n  %s  (%d/%d hits, %d partial, %d miss)", tier_labels[tier], hits, total, partials, misses)
        logger.info("  %-45s %-25s %-25s %s", "Query", "Expected", "Predicted", "Status")
        logger.info("  %s", "-" * 110)
        for r in subset:
            status = "HIT" if r.is_hit else ("PART" if r.is_partial else "MISS")
            exp = ", ".join(r.expected) or "none"
            pred = ", ".join(r.predicted) or "none"
            logger.info("  %-45s %-25s %-25s %s", r.query, exp, pred, status)

    total_hits = sum(1 for r in results if r.is_hit)
    logger.info("\n  Overall: %d/%d hits (%d%%)\n", total_hits, len(results), 100 * total_hits // len(results))


def _log_comparison(baseline: list[EvalResult], finetuned: list[EvalResult]) -> None:
    logger.info("\n%s", "=" * 60)
    logger.info("  COMPARISON — Baseline vs Fine-Tuned")
    logger.info("%s", "=" * 60)
    logger.info("\n  %-25s %-18s %-18s %s", "Tier", "Baseline hits", "Fine-tuned hits", "Delta")
    logger.info("  %s", "-" * 70)
    tier_labels = {1: "Tier 1 — Easy", 2: "Tier 2 — Semantic gap", 3: "Tier 3 — Multi-label"}
    for tier in [1, 2, 3]:
        b_hits, _, _, b_total = _tier_accuracy(baseline, tier)
        f_hits, _, _, f_total = _tier_accuracy(finetuned, tier)
        delta = f_hits - b_hits
        sign = "+" if delta >= 0 else ""
        logger.info("  %-25s %d/%-14d %d/%-14d %s%d", tier_labels[tier], b_hits, b_total, f_hits, f_total, sign, delta)
    logger.info("\n  Headline metric: Tier 2 delta = fine-tuned wins on semantic gap queries\n")


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Intent classifier golden eval")
    parser.add_argument("--baseline", action="store_true", help="Run keyword bag baseline only")
    parser.add_argument("--finetuned", action="store_true", help="Run fine-tuned model only")
    parser.add_argument(
        "--model-path",
        default=os.getenv("FINETUNED_MODEL_PATH", "./models/intent"),
        help="Path to merged fine-tuned model weights",
    )
    args = parser.parse_args()

    run_both = not args.baseline and not args.finetuned

    baseline_results: Optional[list[EvalResult]] = None
    finetuned_results: Optional[list[EvalResult]] = None

    if args.baseline or run_both:
        logger.info("Running keyword-bag baseline...")
        baseline_results = run_intent_eval(_keyword_bag_classify, "Keyword Bag Baseline")
        _log_results("Keyword Bag Baseline", baseline_results)

    if args.finetuned or run_both:
        logger.info("Running fine-tuned model from %s...", args.model_path)
        finetuned_results = run_intent_eval(
            lambda t: _finetuned_classify(t, args.model_path),
            "Fine-Tuned QueryIntentClassifier",
        )
        _log_results("Fine-Tuned QueryIntentClassifier", finetuned_results)

    if baseline_results and finetuned_results:
        _log_comparison(baseline_results, finetuned_results)


if __name__ == "__main__":
    main()
