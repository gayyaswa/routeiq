"""Week 3 agent quality evaluator — stop count, preference match, faithfulness, refinement delta."""
from __future__ import annotations

import math
import time
import uuid
from typing import Optional

from langchain_core.messages import ToolMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from eval.agent_eval_queries import PREFERENCE_KEYWORDS


class AgentEvaluator:
    """Evaluates Day Trip Planner agent quality across single-pass and refinement queries (Strategy pattern)."""

    def __init__(self, graph) -> None:
        self._graph = graph
        self._last_config: Optional[dict] = None

    def _stop_text(self, stop: dict) -> str:
        activities = stop.get("activities") or []
        parts = [
            stop.get("name") or "",
            stop.get("why_visit") or "",
            stop.get("category") or "",
            " ".join(activities),
        ]
        return " ".join(parts).lower()

    def run_plan(self, query: dict) -> tuple[Optional[dict], list, float]:
        initial_state = {
            "city": query["city"],
            "preferences": query["preferences"],
            "time_budget_hours": query["hours"],
            "start_time": query["start_time"],
            "messages": [],
            "draft_itinerary": None,
            "route_coords": None,
            "approved": False,
            "narrative": None,
        }
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        self._last_config = config

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

    def run_refine(self, feedback: str) -> tuple[Optional[dict], list]:
        try:
            for _ in self._graph.stream(
                Command(resume={"approved": False, "feedback": feedback}),
                config=self._last_config,
            ):
                pass
        except GraphInterrupt:
            pass

        snapshot = self._graph.get_state(self._last_config)
        draft = snapshot.values.get("draft_itinerary")
        messages = snapshot.values.get("messages", [])
        return draft, messages

    def score_plan(
        self,
        query: dict,
        draft: Optional[dict],
        messages: list,
        planning_time_s: float,
    ) -> dict:
        if draft is None:
            return {
                "stop_count": 0,
                "preference_match_rate": 0.0,
                "faithfulness_rate": 0.0,
                "tool_call_count": 0,
                "pass_fail": "FAIL",
                "planning_time_s": round(planning_time_s, 1),
                "error": "pipeline error",
            }

        stops = draft.get("stops") or []
        stop_count = len(stops)

        prefs = query.get("preferences", [])
        if prefs:
            matched = sum(
                1
                for pref in prefs
                if any(
                    kw in self._stop_text(s)
                    for s in stops
                    for kw in PREFERENCE_KEYWORDS.get(pref, [pref])
                )
            )
            pref_match = matched / len(prefs)
        else:
            pref_match = 1.0

        faithful_stops = sum(
            1
            for s in stops
            if s.get("visitor_quote") and s.get("why_visit") and (s.get("rating") or 0) > 0
        )
        faithfulness = faithful_stops / stop_count if stop_count else 0.0

        tool_call_count = sum(1 for m in messages if isinstance(m, ToolMessage))

        min_stops = math.floor(query.get("hours", 8) / 2)
        pass_fail = (
            "PASS"
            if stop_count >= min_stops and pref_match >= 0.5 and faithfulness >= 0.5
            else "FAIL"
        )

        return {
            "stop_count": stop_count,
            "preference_match_rate": round(pref_match, 3),
            "faithfulness_rate": round(faithfulness, 3),
            "tool_call_count": tool_call_count,
            "pass_fail": pass_fail,
            "planning_time_s": round(planning_time_s, 1),
            "error": None,
        }

    def score_refinement(
        self,
        query: dict,
        before_draft: Optional[dict],
        after_draft: Optional[dict],
    ) -> dict:
        before_stops = (before_draft or {}).get("stops") or []
        after_stops = (after_draft or {}).get("stops") or []

        before_names = {s.get("name", "").lower() for s in before_stops}
        after_names = {s.get("name", "").lower() for s in after_stops}

        union = before_names | after_names
        intersection = before_names & after_names
        jaccard = len(intersection) / len(union) if union else 1.0
        delta_rate = 1.0 - jaccard

        beach_kws = PREFERENCE_KEYWORDS.get("beaches", [])
        museum_kws = PREFERENCE_KEYWORDS.get("museums", [])

        before_beach = sum(
            1 for s in before_stops if any(kw in self._stop_text(s) for kw in beach_kws)
        )
        after_beach = sum(
            1 for s in after_stops if any(kw in self._stop_text(s) for kw in beach_kws)
        )
        before_museum = sum(
            1 for s in before_stops if any(kw in self._stop_text(s) for kw in museum_kws)
        )
        after_museum = sum(
            1 for s in after_stops if any(kw in self._stop_text(s) for kw in museum_kws)
        )

        preference_gained = after_beach > before_beach
        preference_lost = after_museum < before_museum

        if preference_gained and preference_lost:
            verdict = "YES"
        elif preference_gained or preference_lost:
            verdict = "PARTIAL"
        else:
            verdict = "NO"

        return {
            "before_stop_count": len(before_stops),
            "after_stop_count": len(after_stops),
            "before_beach_count": before_beach,
            "after_beach_count": after_beach,
            "before_museum_count": before_museum,
            "after_museum_count": after_museum,
            "delta_rate": round(delta_rate, 3),
            "preference_gained": preference_gained,
            "preference_lost": preference_lost,
            "verdict": verdict,
        }

    def run_all(
        self, queries: list[dict]
    ) -> tuple[list[dict], Optional[dict]]:
        rows: list[dict] = []
        refinement_result: Optional[dict] = None

        for q in queries:
            print(f"\n  [Query {q['id']}] {q['city']} | {q['preferences']} | {q['hours']}h")
            draft, messages, elapsed = self.run_plan(q)
            score = self.score_plan(q, draft, messages, elapsed)
            score["id"] = q["id"]
            score["city"] = q["city"]
            score["preferences"] = q["preferences"]
            rows.append(score)

            status = score["pass_fail"]
            print(
                f"    {status} stops={score['stop_count']} pref={score['preference_match_rate']:.0%} "
                f"faith={score['faithfulness_rate']:.0%} t={score['planning_time_s']}s tools={score['tool_call_count']}"
            )

            if q.get("refine_feedback"):
                print(f"    Refining: {q['refine_feedback']}")
                before_draft = draft
                after_draft, _ = self.run_refine(q["refine_feedback"])
                refinement_result = self.score_refinement(q, before_draft, after_draft)
                print(
                    f"    Refinement verdict={refinement_result['verdict']} "
                    f"delta={refinement_result['delta_rate']:.0%} "
                    f"beach {refinement_result['before_beach_count']}→{refinement_result['after_beach_count']} "
                    f"museum {refinement_result['before_museum_count']}→{refinement_result['after_museum_count']}"
                )

        return rows, refinement_result
