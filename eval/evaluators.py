"""Week 4 activity-aware evaluators — activity_recall and activity_coverage metrics.

Designed to work alongside the existing AgentEvaluator (Week 3) metrics.
"""
from __future__ import annotations
import json
import math
import time
import uuid
from typing import Optional

from langchain_core.messages import ToolMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from eval.langsmith_dataset import ACTIVITY_KEYWORDS


def _stop_text(stop: dict) -> str:
    parts = [
        stop.get("name") or "",
        stop.get("why_visit") or "",
        stop.get("category") or "",
        stop.get("visitor_quote") or "",
        " ".join(stop.get("activities") or []),
    ]
    return " ".join(parts).lower()


def score_activity_recall(
    requested_activities: list[str],
    itinerary_stops: list[dict],
    tool_messages: list,
) -> float:
    """Fraction of requested activities that appear in the itinerary.

    Priority: check select_pois_for_day ToolMessage matched_activities first
    (ground-truth from the classifier), then fall back to keyword matching
    in stop text (for cases where find_city_pois was used instead).
    Returns 1.0 when no activities are requested (vacuous recall).
    """
    if not requested_activities:
        return 1.0

    covered: set[str] = set()

    # Pass 1 — from select_pois_for_day ToolMessage (matched_activities field)
    for msg in tool_messages:
        if isinstance(msg, ToolMessage) and msg.name == "select_pois_for_day":
            try:
                stops_data = json.loads(msg.content)
                for s in (stops_data if isinstance(stops_data, list) else []):
                    covered.update(s.get("matched_activities") or [])
            except Exception:
                pass

    # Pass 2 — keyword search in stop text (catches find_city_pois path)
    for activity in requested_activities:
        if activity in covered:
            continue
        keywords = ACTIVITY_KEYWORDS.get(activity, [activity])
        for stop in itinerary_stops:
            text = _stop_text(stop)
            if any(kw in text for kw in keywords):
                covered.add(activity)
                break

    return len(covered & set(requested_activities)) / len(requested_activities)


def score_activity_coverage(
    requested_activities: list[str],
    itinerary_stops: list[dict],
) -> float:
    """Fraction of itinerary stops that mention at least one requested activity.

    Returns 0.0 when no activities are requested or no stops produced.
    """
    if not requested_activities or not itinerary_stops:
        return 0.0

    all_keywords = [
        kw
        for activity in requested_activities
        for kw in ACTIVITY_KEYWORDS.get(activity, [activity])
    ]
    covered_stops = sum(
        1
        for stop in itinerary_stops
        if any(kw in _stop_text(stop) for kw in all_keywords)
    )
    return covered_stops / len(itinerary_stops)


class ActivityEvaluator:
    """Evaluates activity recall and coverage for the Week 4 day trip planner (Strategy pattern)."""

    def __init__(self, graph) -> None:
        self._graph = graph

    def run_plan(self, query: dict) -> tuple[Optional[dict], list, float]:
        """Run the planner for one query; return (draft_itinerary, messages, elapsed_s)."""
        initial_state = {
            "city": query["city"],
            "preferences": query.get("preferences", []),
            "time_budget_hours": query.get("hours", 8.0),
            "start_time": query.get("start_time", "9:00 AM"),
            "activities": query.get("activities", []),
            "user_context": query.get("user_context", ""),
            "messages": [],
            "draft_itinerary": None,
            "route_coords": None,
            "approved": False,
            "narrative": None,
            "activity_fallback_note": None,
        }
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        t0 = time.time()
        try:
            for _ in self._graph.stream(initial_state, config=config):
                pass
        except GraphInterrupt:
            pass
        elapsed = time.time() - t0

        snapshot = self._graph.get_state(config)
        draft = snapshot.values.get("draft_itinerary")
        messages = snapshot.values.get("messages", [])
        return draft, messages, elapsed

    def score(self, query: dict, draft: Optional[dict], messages: list, elapsed: float) -> dict:
        """Compute all activity-aware metrics for a single query result."""
        activities = query.get("activities", [])
        stops = (draft or {}).get("stops") or []
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]

        recall = score_activity_recall(activities, stops, tool_msgs)
        coverage = score_activity_coverage(activities, stops)

        stop_count = len(stops)
        min_stops = math.floor(query.get("hours", 8.0) / 2)

        expected_min_recall = query.get("expected_min_recall", 0.5)
        recall_pass = recall >= expected_min_recall if activities else True
        count_pass = stop_count >= min_stops

        return {
            "id": query["id"],
            "city": query["city"],
            "activities": activities,
            "stop_count": stop_count,
            "activity_recall": round(recall, 3),
            "activity_coverage": round(coverage, 3),
            "tool_call_count": len(tool_msgs),
            "elapsed_s": round(elapsed, 1),
            "recall_pass": recall_pass,
            "count_pass": count_pass,
            "pass_fail": "PASS" if (recall_pass and count_pass) else "FAIL",
        }

    def run_all(self, queries: list[dict]) -> list[dict]:
        rows: list[dict] = []
        for q in queries:
            act_str = ", ".join(q.get("activities") or []) or "none"
            print(f"\n  [Q{q['id']}] {q['city']} | activities={act_str}")
            draft, messages, elapsed = self.run_plan(q)
            row = self.score(q, draft, messages, elapsed)
            rows.append(row)
            print(
                f"    {row['pass_fail']} stops={row['stop_count']} "
                f"recall={row['activity_recall']:.0%} coverage={row['activity_coverage']:.0%} "
                f"t={row['elapsed_s']}s"
            )
        return rows
