"""Tool routing eval dataset — 8 cases that verify the correct POI discovery tool is called.

Rule:
  activities non-empty  →  first POI tool must be select_pois_for_day
  activities empty      →  first POI tool must be find_city_pois

Cases r1–r4: activities set (expect select_pois_for_day).
Cases r5–r8: activities empty (expect find_city_pois).

All cities are in the Bay Area KG master (pre-loaded, no Overpass fetch at eval time).
"""

TOOL_ROUTING_QUERIES: list[dict] = [
    # ── Activities set → select_pois_for_day ────────────────────────────────
    {
        "id": "r1",
        "city": "San Francisco, CA",
        "activities": ["hiking"],
        "user_context": "scenic coastal hiking",
        "preferences": ["nature"],
        "hours": 8.0,
        "start_time": "9:00 AM",
        "expected_tool": "select_pois_for_day",
        "notes": "Exact user scenario that triggered the bug — coastal hiking must call select_pois_for_day",
    },
    {
        "id": "r2",
        "city": "San Francisco, CA",
        "activities": ["hiking", "kids"],
        "user_context": "scenic coastal hiking and family trails",
        "preferences": ["nature", "family"],
        "hours": 8.0,
        "start_time": "9:00 AM",
        "expected_tool": "select_pois_for_day",
        "notes": "Multi-activity — both hiking and kids must route through select_pois_for_day",
    },
    {
        "id": "r3",
        "city": "Oakland, CA",
        "activities": ["biking"],
        "user_context": "urban bike trails",
        "preferences": ["nature", "outdoor"],
        "hours": 6.0,
        "start_time": "9:00 AM",
        "expected_tool": "select_pois_for_day",
        "notes": "Biking activity in Oakland — must call select_pois_for_day",
    },
    {
        "id": "r4",
        "city": "San Jose, CA",
        "activities": ["kids"],
        "user_context": "family day with young children",
        "preferences": ["family"],
        "hours": 6.0,
        "start_time": "10:00 AM",
        "expected_tool": "select_pois_for_day",
        "notes": "Kids activity — must call select_pois_for_day",
    },
    # ── Activities empty → find_city_pois ────────────────────────────────────
    {
        "id": "r5",
        "city": "San Francisco, CA",
        "activities": [],
        "user_context": "",
        "preferences": ["nature", "history"],
        "hours": 8.0,
        "start_time": "9:00 AM",
        "expected_tool": "find_city_pois",
        "notes": "No activities, scenic preferences — must call find_city_pois",
    },
    {
        "id": "r6",
        "city": "Oakland, CA",
        "activities": [],
        "user_context": "scenic views",
        "preferences": ["nature"],
        "hours": 6.0,
        "start_time": "9:00 AM",
        "expected_tool": "find_city_pois",
        "notes": "user_context present but no activity keywords — must call find_city_pois",
    },
    {
        "id": "r7",
        "city": "Berkeley, CA",
        "activities": [],
        "user_context": "",
        "preferences": ["history", "art"],
        "hours": 6.0,
        "start_time": "10:00 AM",
        "expected_tool": "find_city_pois",
        "notes": "No activities, history/art preferences — must call find_city_pois",
    },
    {
        "id": "r8",
        "city": "San Jose, CA",
        "activities": [],
        "user_context": "architecture walk",
        "preferences": ["architecture"],
        "hours": 6.0,
        "start_time": "9:00 AM",
        "expected_tool": "find_city_pois",
        "notes": "No activity keywords in user_context — must call find_city_pois",
    },
]
