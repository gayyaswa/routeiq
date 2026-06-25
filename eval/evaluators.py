"""Week 4 activity-aware evaluators — activity_recall, activity_coverage, tool_routing metrics.

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

# POI discovery tools — exactly one of these must be called first.
_POI_DISCOVERY_TOOLS: frozenset[str] = frozenset({"select_pois_for_day", "find_city_pois"})

_MATCH_JUDGE_PROMPT = """\
Activity requested: {activity}
POI: {poi_name}
Description: {description}

Rate 1-5 how well this POI suits the requested activity:
1 = Unrelated / misleading
2 = Tenuous connection
3 = Reasonable but not ideal
4 = Good match
5 = Excellent, clearly designed for this activity

Reply with only a single integer 1-5."""


def _stop_text(stop: dict) -> str:
    parts = [
        stop.get("name") or "",
        stop.get("why_visit") or "",
        stop.get("category") or "",
        stop.get("visitor_quote") or "",
        " ".join(stop.get("activities") or []),
    ]
    return " ".join(parts).lower()


def score_tool_routing(activities: list[str], tool_messages: list) -> dict:
    """Check whether the correct POI discovery tool was called first.

    Rule:
      activities non-empty  →  first POI tool must be select_pois_for_day
      activities empty      →  first POI tool must be find_city_pois

    Returns:
      expected_tool        — what *should* have been called
      actual_first_poi_tool — what was actually called first (or "none")
      routing_pass         — True iff actual matches expected
    """
    first_poi_tool = next(
        (m.name for m in tool_messages if isinstance(m, ToolMessage) and m.name in _POI_DISCOVERY_TOOLS),
        None,
    )
    expected = "select_pois_for_day" if activities else "find_city_pois"
    return {
        "expected_tool": expected,
        "actual_first_poi_tool": first_poi_tool or "none",
        "routing_pass": first_poi_tool == expected,
    }


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


def score_enrichment_quality(tool_messages: list) -> dict:
    """Measure how much real data the rating provider returned for this run.

    Reads the rate_pois ToolMessage and counts what fraction of the enriched
    stops have a real rating, at least one review snippet, and at least one photo.

    Returns:
        pct_rated         — fraction of stops with a numeric rating (vs. None)
        pct_with_reviews  — fraction of stops with at least one review snippet
        pct_with_photos   — fraction of stops with at least one photo URL
        avg_rating        — mean rating across rated stops; None if no ratings at all
    """
    _empty = {"pct_rated": 0.0, "pct_with_reviews": 0.0, "pct_with_photos": 0.0, "avg_rating": None}
    rate_msg = next(
        (m for m in tool_messages if isinstance(m, ToolMessage) and m.name == "rate_pois"),
        None,
    )
    if rate_msg is None:
        return _empty
    try:
        stops = json.loads(rate_msg.content)
    except Exception:
        return _empty
    if not stops:
        return _empty

    n = len(stops)
    rated = [s for s in stops if s.get("rating") is not None]
    with_reviews = [s for s in stops if s.get("all_snippets")]
    with_photos = [s for s in stops if s.get("photo_urls")]
    avg_rating = sum(s["rating"] for s in rated) / len(rated) if rated else None

    return {
        "pct_rated": round(len(rated) / n, 3),
        "pct_with_reviews": round(len(with_reviews) / n, 3),
        "pct_with_photos": round(len(with_photos) / n, 3),
        "avg_rating": round(avg_rating, 2) if avg_rating is not None else None,
    }


def score_activity_match_quality(
    activities: list[str],
    itinerary_stops: list[dict],
    llm,
    tool_messages: Optional[list] = None,
) -> dict:
    """Measure how good the activity-matched stops actually are (Track 1 only).

    Only Track 1 stops — those where the classifier set matched_activities — are
    scored. Track 2 scenic fill stops are never included in either metric.

    pct_with_evidence (code-based):
        Fraction of Track 1 stops where the classifier also wrote down *why* the
        POI suits the activity (non-empty activity_evidence). A high score means
        the agent's activity matching is interpretable; a low score means you have
        to take the matches on faith.

    avg_match_quality (LLM-as-judge):
        An LLM rates each Track 1 stop 1–5 on how well it suits the requested
        activity, using the stop's name and description as context. The scores are
        averaged. A 5 means "obviously right"; a 3 means "technically related but
        the agent is stretching"; a 1 means "unrelated".

    Prefers matched-stop data from the rate_pois ToolMessage (has both
    matched_activities and activity_evidence) and falls back to itinerary_stops.
    Returns avg_match_quality=None when llm is None (graceful degradation).
    """
    if not activities:
        return {"pct_with_evidence": 0.0, "avg_match_quality": None}

    # Prefer rate_pois ToolMessage — it carries matched_activities + activity_evidence.
    matched_stops: list[dict] = []
    if tool_messages:
        rate_msg = next(
            (m for m in tool_messages if isinstance(m, ToolMessage) and m.name == "rate_pois"),
            None,
        )
        if rate_msg:
            try:
                matched_stops = [
                    s for s in json.loads(rate_msg.content)
                    if s.get("matched_activities")
                ]
            except Exception:
                pass

    if not matched_stops:
        matched_stops = [s for s in itinerary_stops if s.get("matched_activities")]

    if not matched_stops:
        return {"pct_with_evidence": 0.0, "avg_match_quality": None}

    pct_with_evidence = round(
        sum(1 for s in matched_stops if s.get("activity_evidence")) / len(matched_stops), 3
    )

    if llm is None:
        return {"pct_with_evidence": pct_with_evidence, "avg_match_quality": None}

    scores: list[int] = []
    for stop in matched_stops:
        activity = (stop.get("matched_activities") or activities)[0]
        description = stop.get("why_visit") or stop.get("activity_evidence") or ""
        prompt_text = _MATCH_JUDGE_PROMPT.format(
            activity=activity,
            poi_name=stop.get("name", "Unknown"),
            description=description,
        )
        try:
            response = llm.invoke(prompt_text)
            raw = (response.content if hasattr(response, "content") else str(response)).strip()
            digit = next((c for c in raw if c in "12345"), None)
            if digit:
                scores.append(int(digit))
        except Exception:
            pass

    avg_match_quality = round(sum(scores) / len(scores), 2) if scores else None
    return {"pct_with_evidence": pct_with_evidence, "avg_match_quality": avg_match_quality}


class ActivityEvaluator:
    """Evaluates activity recall and coverage for the Week 4 day trip planner (Strategy pattern)."""

    def __init__(self, graph, llm=None) -> None:
        self._graph = graph
        self._llm = llm

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
        routing = score_tool_routing(activities, tool_msgs)
        enrichment = score_enrichment_quality(tool_msgs)
        match_quality = score_activity_match_quality(
            activities, stops, self._llm, tool_messages=tool_msgs
        )

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
            "routing_pass": routing["routing_pass"],
            "expected_tool": routing["expected_tool"],
            "actual_first_poi_tool": routing["actual_first_poi_tool"],
            "pass_fail": "PASS" if (recall_pass and count_pass) else "FAIL",
            # Enrichment quality (from rate_pois ToolMessage)
            "pct_rated": enrichment["pct_rated"],
            "pct_with_reviews": enrichment["pct_with_reviews"],
            "pct_with_photos": enrichment["pct_with_photos"],
            "avg_rating": enrichment["avg_rating"],
            # Activity match quality (Track 1 stops only)
            "pct_with_evidence": match_quality["pct_with_evidence"],
            "avg_match_quality": match_quality["avg_match_quality"],
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
