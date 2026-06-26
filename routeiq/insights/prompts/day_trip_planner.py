from langchain_core.prompts import ChatPromptTemplate

_SYSTEM = """You are a day-trip itinerary planner. You build realistic, geographically ordered \
itineraries for a single city using real POI data from tools.

Faithfulness rules — enforce strictly:
- visitor_quote: pick the single most vivid sentence from all_snippets; prefix with the \
review_source name (e.g. "Visitors on TripAdvisor say: '...'"). Never invent a quote.
- visitor_summary: write 1–2 sentences synthesizing the overall sentiment across all snippets \
in all_snippets. Ground every claim in the snippets — do not invent details.
- why_visit: one factual sentence grounded in query_poi_context output when available; \
fall back to the POI's Wikipedia description field. Prefer context that mentions nearby \
landmarks or knowledge graph relationships. Never invent facts.
- activities: derive only from the Wikipedia description AND review snippets. \
Use the POI's OSM subtype as a last-resort fallback for one generic activity. \
Never invent activities.
- Schedule stops in geographic order to minimize travel time between them.
- Output ONLY the JSON block — no markdown fences, no commentary, no explanation.
"""

_HUMAN = """Plan a {hours}-hour day trip in {city} starting at {start_time}.
Preferences: {preferences}

Tool call order:
1. find_city_pois — get POIs for the city
2. rate_pois — enrich with ratings and reviews; keep top candidates
3. enrich_poi_details — fetch Wikipedia context for the top 8 POIs
4. estimate_visit_duration — get visit duration per stop subtype

Your job is to SELECT the best 8–10 stops that match the preferences and variety of
experience. Do NOT try to calculate travel times or fit stops within the time budget
yourself — road-based scheduling is handled automatically after you output the itinerary.
Set arrival_time and departure_time to placeholder values ("TBD"); they will be replaced.

Output format (JSON only, no fences):
{{
  "city": "{city}",
  "date": "today",
  "total_hours": {hours},
  "stops": [
    {{
      "order": 1,
      "name": "<POI name>",
      "category": "<OSM category>",
      "lat": 0.0,
      "lon": 0.0,
      "arrival_time": "TBD",
      "departure_time": "TBD",
      "visit_duration_min": 90,
      "why_visit": "<one factual Wikipedia sentence>",
      "visitor_quote": "<review_source>: '<single most vivid snippet from all_snippets>'",
      "visitor_summary": "<1-2 sentence synthesis of overall sentiment from all_snippets>",
      "activities": ["<activity 1>", "<activity 2>"],
      "rating": 4.5,
      "review_count": 1200,
      "review_source": "<TripAdvisor | Foursquare | Unknown>",
      "photo_urls": ["<url1>", "<url2>"],
      "image_url": "<Wikipedia thumbnail fallback>",
      "hours": "<opening hours string or null>"
    }}
  ],
  "narrative": null
}}
"""

DAY_TRIP_PLANNER_PROMPT_V1 = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM),
    ("human", _HUMAN),
])

_HUMAN_V2 = """Plan a {hours}-hour day trip in {city} starting at {start_time}.
Preferences: {preferences}
Activities requested: {activities}
User context: {user_context}

Tool call order:
1. If activities are non-empty → call select_pois_for_day (handles activity matching + scenic fills).
   Otherwise → call find_city_pois to get all POIs.
2. rate_pois — enrich with ratings and reviews; pass the full JSON output from step 1 as poi_list_json.
   rate_pois already returns: description (Wikipedia text), image_url, and visit_duration_min.
   Do NOT call enrich_poi_details or estimate_visit_duration — the data is already present.

Your job is to SELECT the best 8–10 stops. For activity stops (track="activity"):
- Open the description with the specific matched activity.
- Cite activity_evidence when present.
- Do NOT claim any activity not listed in matched_activities.
For scenic stops (track="scenic"): describe scenic quality and highlights.
Do NOT try to calculate travel times — scheduling is handled automatically.
Set arrival_time and departure_time to "TBD".

Output format (JSON only, no fences):
{{
  "city": "{city}",
  "date": "today",
  "total_hours": {hours},
  "stops": [
    {{
      "order": 1,
      "name": "<POI name>",
      "category": "<OSM category>",
      "lat": 0.0,
      "lon": 0.0,
      "arrival_time": "TBD",
      "departure_time": "TBD",
      "visit_duration_min": 90,
      "why_visit": "<one factual Wikipedia sentence>",
      "visitor_quote": "<review_source>: '<single most vivid snippet from all_snippets>'",
      "visitor_summary": "<1-2 sentence synthesis of overall sentiment from all_snippets>",
      "activities": ["<copy matched_activities from select_pois_for_day if present, else derive from Wikipedia/reviews>"],
      "rating": 4.5,
      "review_count": 1200,
      "review_source": "<TripAdvisor | Foursquare | Unknown>",
      "photo_urls": ["<url1>", "<url2>"],
      "image_url": "<Wikipedia thumbnail fallback>",
      "hours": "<opening hours string or null>"
    }}
  ],
  "narrative": null
}}
"""

# V2 — two-track activity-aware planning
DAY_TRIP_PLANNER_PROMPT_V2 = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM),
    ("human", _HUMAN_V2),
])

_HUMAN_V3 = """Plan a {hours}-hour day trip in {city} starting at {start_time}.
Preferences: {preferences}
Activities requested: {activities}
User context: {user_context}

Tool call order:
1. If activities are non-empty → call select_pois_for_day (handles activity matching + scenic fills).
   Otherwise → call find_city_pois to get all POIs.
2. rate_pois — enrich with ratings, reviews, and Wikipedia descriptions; pass the full JSON
   output from step 1 as poi_list_json.
   rate_pois already returns: description (Wikipedia text), image_url, and visit_duration_min.
   Do NOT call enrich_poi_details or estimate_visit_duration — the data is already present.
3. query_poi_context — pass your preferences list and the full rate_pois JSON output.
   Returns KG-enriched context: semantic match scores, Wikipedia evidence, city/region from
   the knowledge graph, and nearby POI relationships.
   Use this context to write specific, grounded why_visit sentences.

Your job is to SELECT the best 8–10 stops. For activity stops (track="activity"):
- Open the description with the specific matched activity.
- Cite activity_evidence when present.
- Do NOT claim any activity not listed in matched_activities.
For scenic stops (track="scenic"): describe scenic quality and highlights.
Do NOT try to calculate travel times — scheduling is handled automatically.
Set arrival_time and departure_time to "TBD".

Output format (JSON only, no fences):
{{
  "city": "{city}",
  "date": "today",
  "total_hours": {hours},
  "stops": [
    {{
      "order": 1,
      "name": "<POI name>",
      "category": "<OSM category>",
      "lat": 0.0,
      "lon": 0.0,
      "arrival_time": "TBD",
      "departure_time": "TBD",
      "visit_duration_min": 90,
      "why_visit": "<one factual sentence from query_poi_context or Wikipedia description>",
      "visitor_quote": "<review_source>: '<single most vivid snippet from all_snippets>'",
      "visitor_summary": "<1-2 sentence synthesis of overall sentiment from all_snippets>",
      "activities": ["<copy matched_activities from select_pois_for_day if present, else derive from Wikipedia/reviews>"],
      "rating": 4.5,
      "review_count": 1200,
      "review_source": "<TripAdvisor | Foursquare | Unknown>",
      "photo_urls": ["<url1>", "<url2>"],
      "image_url": "<Wikipedia thumbnail fallback>",
      "hours": "<opening hours string or null>"
    }}
  ],
  "narrative": null
}}
"""

# V3 — adds query_poi_context (Vector RAG + KG enrichment) to Day Trip planning
DAY_TRIP_PLANNER_PROMPT_V3 = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM),
    ("human", _HUMAN_V3),
])

DAY_TRIP_PLANNER_PROMPT = DAY_TRIP_PLANNER_PROMPT_V3
