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
    → LangGraph Pipeline
        [parse]   Query Parser (Claude)          extract origin, destination, preferences
        [graph]   Graph Layer (OSMnx + NetworkX) shortest path + POI spatial join + detour scoring
        [rag]     RAG Layer (ChromaDB)           landmark descriptions fetched and indexed
        [narrate] Response (Claude)              narrative + structured stop list
        [edge]    Conditional edges              handle no POIs / long route / unparseable query
    → UI                                         map with route + markers + stop cards
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
  pipeline.py                     LangGraph pipeline — nodes: parse → graph → rag → narrate, with conditional edges
docs/
  plan-day1.md                    Day 1 architecture decisions
prompts.md                        Running log of every prompt — update after every session
tests/                            Unit tests
```

## Day-by-day plan

### Day 1 — Graph foundation
- [ ] OSMnx: load road network for Austin → San Antonio corridor
- [ ] NetworkX: shortest path (A*) working
- [ ] POI spatial join: tourism/historic/natural features along route
- [ ] Folium map: verify route + POIs visually

### Day 2 — Graph RAG core + LangGraph pipeline
- [ ] Detour cost scoring per POI
- [ ] Top-N POI selection with category filtering
- [ ] NL query parser (Claude via LangChain): extract origin, destination, preferences
- [ ] Wire LangGraph state machine: parse → graph → rag → narrate nodes with shared state
- [ ] Conditional edges: no POIs found, route too long, unparseable query

### Day 3 — RAG layer + vector baseline + images
- [ ] Wikipedia intro fetch per POI (text description)
- [ ] Wikipedia thumbnail image URL fetch per POI — stored in POI.image_url
- [ ] ChromaDB: index POI documents (local embeddings)
- [ ] Retrieval by POI ID → rich context for Claude
- [ ] Claude generates narrative from route + POI contexts
- [ ] Build vector-only retrieval baseline (pure semantic, no graph) — needed for Day 4 comparison

### Day 4 — UI + evaluation
- [ ] Map: route polyline + color-coded POI markers
- [ ] Stop cards: POI name + detour time + why visit + Wikipedia thumbnail image
- [ ] 10-query comparison: GraphRAG results vs. vector-only baseline — document when each wins
- [ ] Edge cases fully handled via LangGraph conditional edges

### Day 5 — Demo prep + submission
- [ ] 4 canned scenic demo queries across different Texas routes:
  -  Austin → San Antonio (historic towns, natural springs)
  -  Austin → Fredericksburg → San Antonio (Hill Country: wineries, Enchanted Rock, Luckenbach)
  -  San Antonio → Marble Falls (Highland Lakes, swimming holes)
  -  Houston → Austin (bluebonnet trail, Round Top)
- [ ] Each demo query shows: route map + stop cards with real Wikipedia images
- [ ] README with architecture diagram
- [ ] Fill out RAG framework one-liner + framework table (for Google Doc)
- [ ] Google Doc: project overview, datasets, prompts, iterations, learnings
- [ ] Record demo (≤ 5 min)
- [ ] Submit: GitHub link + Google Doc + demo recording

## Submission requirements (Week 2)

| Deliverable | What it needs |
|---|---|
| Demo recording | ≤ 5 min, walk through app live, explain Graph RAG vs vector comparison |
| GitHub repo | Clean code, requirements.txt, README with architecture diagram |
| Google Doc | Project overview, datasets (OSM + Wikipedia), prompts used, iterations, learnings |
| Evaluation | 10-query GraphRAG vs. vector-only comparison with analysis of when each wins |

## RAG framework one-liner (for submission doc)

My RAG app helps travelers answer scenic route questions from OpenStreetMap road network
graphs and Wikipedia landmark data in a map UI, combining spatial graph retrieval with
vector search for high-faithfulness stop recommendations.

## Prompt-driven development conventions

### Prompt registry structure
```
routeiq/insights/
  prompts/
    __init__.py              re-exports all active prompts
    system.py                global system prompt — model persona + faithfulness rules
    query_parser.py          NL query → structured intent
    narrative.py             route + POIs → story
    fallback.py              error / no-result edge cases
  examples/
    query_parser_examples.py  few-shot examples as data (not hardcoded in prompts)
```

### Prompt conventions
- One `ChatPromptTemplate` per file — named `{DOMAIN}_PROMPT`
- Version explicitly: `QUERY_PARSER_PROMPT_V1`, `QUERY_PARSER_PROMPT_V2` — keep old versions
- Active version aliased: `QUERY_PARSER_PROMPT = QUERY_PARSER_PROMPT_V2`
- Few-shot examples live in `examples/` as plain dicts — never hardcoded in prompt strings
- System prompt injected once at the top of every prompt — never duplicated
- Prompts are injected as dependencies — never instantiated inside chain methods

### Prompt changelog discipline
- Every prompt change gets a `prompts.md` entry: what changed → why → what improved
- Treat prompt quality regressions like test failures — investigate before shipping
- Prompt version bumps are code changes — commit them with descriptive messages

### Slash commands available
- `/new-prompt <domain>` — scaffold a new prompt file + examples file + test stub
- `/bump-prompt <domain>` — version up an existing prompt (V1 → V2), keeps old version
- `/log-prompt` — append current session's prompt result to prompts.md

## Conventions (carried from Portfolio app, tech-stack agnostic)

### Always do after any code change
- Run `python3 -m pytest tests/ -v` before reporting work done
- If new functions are added to `routeiq/graph/` or `routeiq/routing/`, add unit tests

### Prompt tracking
- After every prompt that produces a meaningful result, append it to `prompts.md`
- Format: Prompt text → What it produced → Key observation

### Adding AI features
- Use LangChain (`langchain-anthropic`, `langchain-core`) and LangGraph (`langgraph`) — not the raw Anthropic SDK
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
| **Pipeline** | LangGraph state machine — named nodes, shared state, conditional edges |
| **Factory** | LLM chain creation, retriever instantiation |
| **Registry** | POI category mappings, scoring weight configs |
| **Dependency Injection** | LLM injected into all AI classes — testable with mocks |

## Tech stack (Week 1 — swap later as needed)

| Component | Tool | Notes |
|---|---|---|
| Road network | OSMnx | Loads any region from OpenStreetMap by name |
| Graph traversal | NetworkX | In-memory A*, no server needed |
| Pipeline orchestration | LangGraph | State machine with named nodes + conditional edges |
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
