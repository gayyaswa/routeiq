from langchain_core.prompts import ChatPromptTemplate
from routeiq.insights.prompts.system import SYSTEM_PROMPT

# V1 — baseline narrative from route + ranked POI context (name/category/detour only)
NARRATIVE_PROMPT_V1 = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """Generate a scenic route narrative for the following trip.

Origin: {origin}
Destination: {destination}
Total distance: {distance_km} km
Estimated drive time: {drive_time_min} minutes

Recommended stops (ranked by interest, spatially verified):
{poi_context}

Write a short, engaging narrative (3-5 sentences) followed by a structured stop list.
Each stop: name | detour time | why visit"""),
])

# V2 — richer narrative using Wikipedia descriptions retrieved by the RAG layer
NARRATIVE_PROMPT_V2 = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """Generate a scenic route narrative for the following trip.

Origin: {origin}
Destination: {destination}
Total distance: {distance_km} km
Estimated drive time: {drive_time_min} minutes

Recommended stops with context (spatially verified, Wikipedia-enriched):
{poi_context}

Each stop entry is formatted as:
  name | category | detour time | description

Instructions:
- Write an engaging opening narrative (3-5 sentences) that sets the mood for the drive.
- Then list each stop with: name | detour time | one sentence on why to visit (drawn from the description).
- Ground every recommendation in the provided descriptions — do not invent facts.
- If a stop has no description, rely on the category and name only."""),
])

# V3 — Graph-enriched context: city, region, nearby POIs from knowledge graph traversal
NARRATIVE_PROMPT_V3 = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """Generate a scenic route narrative for the following trip.

Origin: {origin}
Destination: {destination}
Total distance: {distance_km} km
Estimated drive time: {drive_time_min} minutes

Recommended stops (graph-verified: spatially on route, Wikipedia-enriched):
{poi_context}

Each stop is formatted as:
  name | category | city | region | nearby stops | description excerpt

Instructions:
- Write an engaging opening narrative (3-5 sentences) that captures the character of the route and region.
- List each stop: name | detour time | one sentence why to visit, drawn from the description.
- Mention the region where it adds flavour (e.g. "deep in the Hill Country").
- Ground every fact in the provided context. Do not invent locations or distances."""),
])

NARRATIVE_PROMPT = NARRATIVE_PROMPT_V3  # active version
