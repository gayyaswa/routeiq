# RouteIQ — Claude Code Instructions

## What this project is

A geospatial intelligence assistant that answers natural language route queries and returns
scenic/landmark stops along the way — powered by Graph RAG (road network graph + pathfinding)
and RAG (landmark descriptions from Wikipedia/OSM).

Example query: "Drive from Austin to San Antonio, show me historic towns and natural landmarks"

Run with: TBD (UI framework not yet locked in)
Tests: `python3 -m pytest tests/ -v`

## Architecture

```
NL Query
    → Query Parser (Claude)         extract origin, destination, stop preferences
    → Graph Layer (OSMnx + NetworkX) shortest path + POI spatial join + detour scoring
    → RAG Layer (ChromaDB)           landmark descriptions fetched and indexed
    → Response (Claude)             narrative + structured stop list
    → UI                            map with route + markers + stop cards
```

## File map

```
app.py (or main.py)               Entry point — wired after UI framework is chosen
routeiq/
  graph/                          Road network loading, pathfinding, spatial join
  rag/                            ChromaDB indexing, Wikipedia fetching, retrieval
  routing/                        Route scoring, POI ranking, detour cost
  insights/                       LangChain chains — query parsing + narrative generation
  facade.py                       RouteIQFacade — single entry point for all views
  pipeline.py                     RoutePipeline — query → graph → rag → response
docs/
  plan-day1.md                    Day 1 architecture decisions
prompts.md                        Running log of every prompt — update after every session
tests/                            Unit tests
```

## Day-by-day plan

### Day 1 — Graph foundation
- [ ] OSMnx: load road network for Austin → San Antonio corridor
- [ ] NetworkX: shortest path (A*) working, route plotted on map
- [ ] POI spatial join: tourism/historic/natural features along route

### Day 2 — Graph RAG core
- [ ] Detour cost scoring per POI
- [ ] Top-N POI selection with category filtering
- [ ] NL query parser (Claude): extract origin, destination, preferences
- [ ] Wire: NL → graph traversal → ranked stop list

### Day 3 — RAG layer
- [ ] Wikipedia intro fetch per POI
- [ ] ChromaDB: index POI documents
- [ ] Retrieval by POI ID → rich context for Claude
- [ ] Claude generates narrative from route + POI contexts

### Day 4 — UI + integration
- [ ] Map: route polyline + color-coded POI markers
- [ ] Stop cards: name, detour time, why visit
- [ ] Edge cases: no POIs found, route too long, unparseable query

### Day 5 — Demo prep
- [ ] 3-4 canned demo queries working end-to-end
- [ ] README with architecture diagram
- [ ] Record demo

## Conventions (carried from Portfolio app, tech-stack agnostic)

### Always do after any code change
- Run `python3 -m pytest tests/ -v` before reporting work done
- If new functions are added to `routeiq/graph/` or `routeiq/routing/`, add unit tests

### Prompt tracking
- After every prompt that produces a meaningful result, append it to `prompts.md`
- Format: Prompt text → What it produced → Key observation

### Adding AI features
- Use LangChain (`langchain-anthropic`, `langchain-core`) — not the raw Anthropic SDK
- Default model: `claude-sonnet-4-6` via `ChatAnthropic`
- Inject the LLM as a dependency — create it at the entry point, pass it down
- API key via environment variable (`ANTHROPIC_API_KEY`) with secrets fallback
- AI features must degrade gracefully when no key is present

### Code conventions

#### Module organization
- Business logic in `routeiq/` — domain-named, not generic
- Sub-packages per domain concern: `graph/`, `rag/`, `routing/`, `insights/`
- Each sub-package has an `__init__.py` that re-exports public symbols
- Import from sub-package root, never from internal files:
  - Correct: `from routeiq.graph import RouteGraph`
  - Wrong:   `from routeiq.graph.route_graph import RouteGraph`
- `routeiq/facade.py` and `routeiq/pipeline.py` stay at top level — cross-cutting

#### File naming
- One class per file; filename = full snake_case of the class name
- Function-only modules: short descriptive noun — `engine.py`, `loader.py`, `scorer.py`

#### Class docstrings
Every class must have a one-line docstring stating what it IS and which pattern it implements:
- Correct: `"""Loads and caches OSM road network graphs for a given region (Registry pattern)."""`
- Wrong:   `"""This class loads graphs."""`

#### Inline comments
Only when the WHY is non-obvious: hidden constraints, business rules, non-obvious invariants.
Do not comment what the code does.

## Design patterns (apply when appropriate, do not force)

| Pattern | Where it applies |
|---|---|
| **Facade** | `RouteIQFacade` — single entry point for all views/consumers |
| **Strategy** | Route scoring algorithms, POI ranking strategies, query parsers |
| **Pipeline** | Sequential transforms: query → graph → RAG → response |
| **Factory** | LLM chain creation, retriever instantiation |
| **Registry** | POI category mappings, scoring weight configs |
| **Dependency Injection** | LLM injected into all AI classes — testable with mocks |

## Tech stack (Week 1 — swap later as needed)

| Component | Tool | Notes |
|---|---|---|
| Road network | OSMnx | Loads any region from OpenStreetMap by name |
| Graph traversal | NetworkX | In-memory A*, no server needed |
| Vector store | ChromaDB | Local, no server, LangChain native |
| LLM | Claude Sonnet 4.6 via LangChain | |
| Map rendering | Folium | Swap for any map library |
| UI | TBD | Not locked in — Streamlit, FastAPI+React, or CLI |

Neo4j deferred — add when graph exceeds memory or multi-city persistence is needed.

## Explicitly out of scope (Week 1)

- Real-time traffic / incident data
- Evals framework (Week 2)
- Observability / LangSmith (Week 2)
- Fine-tuning (later)
- Neo4j
- Auth, saved routes, cloud deployment
