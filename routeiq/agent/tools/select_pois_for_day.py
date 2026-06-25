from __future__ import annotations
import dataclasses
import json
import time

from langchain_core.tools import tool

from routeiq.graph.knowledge_graph import get_kg


@tool
def select_pois_for_day(
    city: str,
    requested_activities: list[str],
    user_context: str,
    total_stops: int,
) -> str:
    """Select POIs for a day trip when the user specifies activities (hiking, biking, kids, etc.).

    Uses a two-track merge:
      Track 1 — activity-matched slots: POIs verified to support the requested activities.
      Track 2 — scenic fills: top remaining POIs by scenic score.

    Use this tool instead of find_city_pois when requested_activities is non-empty.
    Pass the returned JSON directly to rate_pois as poi_list_json.

    Args:
        city: City name, e.g. "San Francisco, CA"
        requested_activities: Activities to match, e.g. ["hiking", "kids"]
        user_context: Adjective style phrase, e.g. "scenic coastal hiking" (or "")
        total_stops: Total stops to return (activity slots + scenic fills)

    Returns:
        JSON array of POI dicts (same fields as find_city_pois) plus
        matched_activities and track ("activity" | "scenic") per stop.
    """
    from routeiq.activities.factory import create_activity_classifier, create_ranker
    from routeiq.routing.activity_poi_selector import ActivityPOISelector

    pois = get_kg().get_pois_for_city(city)
    if not pois:
        return json.dumps([])

    from routeiq.timing import log as _tlog
    classifier = create_activity_classifier()
    _t_classify = time.perf_counter()
    classified = classifier.classify_batch(city, pois, requested_activities)
    _tlog(f"select_pois classify_batch={time.perf_counter()-_t_classify:.2f}s activities={requested_activities}")

    ranker = create_ranker(user_context, ratings_available=False)
    selector = ActivityPOISelector()
    selected = selector.select(
        classified,
        requested_activities=requested_activities,
        user_context=user_context,
        ratings={},
        total_stops=total_stops,
        ranker=ranker,
    )

    results = []
    for c in selected:
        entry = dataclasses.asdict(c.poi)
        entry["matched_activities"] = c.matched_activities
        entry["activity_evidence"] = c.activity_evidence
        entry["track"] = "activity" if c.matched_activities else "scenic"
        results.append(entry)

    return json.dumps(results)
