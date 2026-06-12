# RouteIQ Demo Narration Script
**Route:** SF → Sausalito via the Golden Gate Bridge  
**Target:** ≤ 5 minutes  
**Query:** *Drive from San Francisco to Sausalito via the Golden Gate Bridge, show historic sites and bay views*

---

## 0:00 — Open the app

> "This is RouteIQ — a scenic route assistant built on Graph RAG.
> Instead of finding the fastest path, it finds the most interesting one.
> It combines a real OpenStreetMap road network, Wikipedia landmark data,
> and a 3-stage GraphRAG pipeline orchestrated by LangGraph.
> Let me show you how it works."

---

## 0:20 — Click the SF → Sausalito hint button

> "I'll click the SF → Sausalito hint button.
> The query fills in automatically:
> *Drive from San Francisco to Sausalito via the Golden Gate Bridge,
> show historic sites and bay views.*
> Watch the stepper — it shows exactly where we are in the pipeline."

---

## 0:35 — Step 1: Parsing 🔍

> "First, the query parser.
> This uses Claude with **structured output** — not freeform JSON generation,
> but a typed Pydantic model called RouteInput.
> The model is forced through tool use to return exactly three fields:
> origin, destination, and preferences.
> No regex, no code-fence stripping — it either returns a valid object or raises.
>
> Result: origin = San Francisco CA, destination = Sausalito CA,
> preferences = historic sites, bay views."

---

## 1:00 — Step 2: Building the route 🗺️

> "Next, the graph node.
> OSMnx downloads the real Bay Area road network from OpenStreetMap —
> every intersection, every road segment — as a NetworkX graph.
> We run A-star for the shortest path, then draw a 5km corridor buffer around it.
> Everything inside that buffer is a POI candidate.
>
> Before scoring, the pipeline does something the original design was missing:
> it runs a quick **semantic search** on the POI vector database using the preference
> keywords — *historic sites* and *bay views* — and extracts the OSM categories
> those map to: historic, natural, tourism.
> Those become the category filter so only relevant POI types are considered.
>
> POIs are then ranked by three tiers:
> first, whether OSM editors tagged it with a Wikipedia link — a notability signal.
> Second, scenic subtype score — a viewpoint scores 9, a fort scores 7, a memorial scores 3.
> Third, detour cost as a tiebreaker.
> A 2km spread rule prevents five stops clustering in the same neighbourhood."

---

## 1:50 — Step 3: Wikipedia + GraphRAG 📚

> "This is the core of the system — the RAG node runs three stages.
>
> **Stage 1 — vector search.**
> The preferences are embedded and queried against our ChromaDB chunk collection.
> It returns a ranked list of semantically similar POIs —
> you might see Fisherman's Wharf or Mavericks Surf Break near the top,
> and Fort Point further down.
> Pure semantics — no geography yet.
>
> **Stage 2 — graph filter and augment.**
> This is where GraphRAG earns its name.
> The knowledge graph checks which results belong to cities
> within the route's bounding box.
> Fisherman's Wharf is on the wrong side of the bay — dropped.
> Mavericks is down the coast — dropped.
> Fort Point's LOCATED_IN edge points to Sausalito,
> which is inside the SF→Sausalito corridor — it stays.
>
> Then graph augmentation kicks in:
> Fort Point gets enriched with its city, region — North Bay / Marin —
> and its NEAR_POI edges, which include the Golden Gate Bridge
> and Palace of Fine Arts.
> That relationship data goes directly into the context Claude receives.
>
> **Stage 3 — context assembly.**
> Each surviving result becomes one structured line:
> name, category, city, region, nearby POIs, and the Wikipedia evidence chunk.
> That's what makes the narrative geographically accurate —
> the graph acted as a filter and an enricher, not just a lookup."

---

## 3:00 — Step 4: Narrative ✍️

> "Finally, the narrate node streams a Claude-generated narrative token by token —
> you can see it appear live.
> The prompt receives the full assembled context:
> route stats, top POIs, and the GraphRAG-enriched descriptions.
> Claude writes a story, not a list."

---

## 3:20 — Show map + stop cards

> "The result: an animated route on a Folium map,
> colour-coded stop markers — blue for historic, green for natural —
> and stop cards with the Wikipedia thumbnail, a reason to visit,
> and the detour cost in minutes.
> Every stop is traceable to a real OSM entry and a real Wikipedia article.
> Nothing hallucinated."

---

## 3:45 — Switch to Vector Baseline tab

> "Now let me show you why the graph matters.
> I'll switch to the Vector Baseline — pure semantic search
> over the same 95 Bay Area POIs, no road network, no spatial join.
>
> It returns things like Fisherman's Wharf, Mavericks Surf Break,
> History Park — all valid Bay Area landmarks,
> all semantically close to *historic sites and bay views*.
> But none of them are on this route.
>
> GraphRAG wins here because the road network enforces geography.
> The spatial join and the graph bounding box filter act as a hard constraint —
> only stops you can actually reach with a reasonable detour make the cut."

---

## 4:20 — Close

> "That's RouteIQ.
> LangGraph pipeline, structured output parsing,
> semantic preference resolution, 3-stage GraphRAG
> with a spatial knowledge graph, and streaming narrative.
> All data is real: OpenStreetMap roads, Overpass POIs, Wikipedia descriptions.
> The code is on GitHub."

---

## Recording tips

- Hide the terminal — only the Streamlit UI on screen
- Pause on each stepper step long enough to read the label
- Zoom into the stop cards to show Wikipedia images clearly
- Slow-scroll the map before switching to Vector Baseline
- Switch to Vector Baseline tab last — end on the contrast
