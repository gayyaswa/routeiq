# Session 2 Handoff — RouteIQ

## Where we left off

Planning is complete. All decisions are locked. Ready to start Day 1 coding.
The next session should say: "implement Day 1 — read the handoff first."

---

## What was decided this session

### Build track
- **Track 2** (LangChain + LangGraph, code-heavy)
- **Project 3** (Graph RAG) from the Week 2 handout
- Submission: demo recording + GitHub + Google Doc

### Architecture locked
- **LangGraph** state machine for the pipeline (parse → graph → rag → narrate nodes)
- **ChromaDB** local embeddings — zero API dependency, one-line swap later
- **Claude Sonnet 4.6** via Anthropic API for LLM calls
- **osmnx>=2.0** pinned in requirements.txt — eliminates version shim complexity
- DI pattern means any provider (Nebius, OpenAI) is a one-line swap at entry point

### Nebius question outstanding
- Email drafted to Tanish (cohort instructor) — not sent yet
- Subject: "Nebius requirement — clarification needed"
- Question: does Claude API satisfy the requirement, or must a call go through Nebius?
- Does NOT reveal project name or tech stack details

### Prompt infrastructure built
- `routeiq/insights/prompts/` — system, query_parser, narrative, fallback prompts (all V1)
- `routeiq/insights/examples/` — few-shot examples for query parser
- `.claude/commands/` — `/new-prompt`, `/bump-prompt`, `/log-prompt` slash commands
- `~/.claude/commands/` — same commands at user level (works across all projects)

### Day 3 scope expanded
- Wikipedia image URL fetch per POI (thumbnail) → stored in `POI.image_url`
- Stop cards on Day 4 show real Wikipedia images alongside name + detour + why visit

### Day 5 demo routes planned (4 scenic Texas routes)
1. Austin → San Antonio (historic towns, natural springs)
2. Austin → Fredericksburg → San Antonio (Hill Country: wineries, Enchanted Rock, Luckenbach)
3. San Antonio → Marble Falls (Highland Lakes, swimming holes)
4. Houston → Austin (bluebonnet trail, Round Top)

---

## Exact next steps (Day 1 implementation)

Run in this order:

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest tests/ -v
python3 day1_verify.py
open day1_map.html
```

### Files to create (in order)

1. `routeiq/graph/route_result.py` — RouteResult dataclass
2. `routeiq/graph/poi.py` — POI dataclass (includes wikipedia_tag + image_url)
3. `routeiq/graph/graph_loader.py` — GraphLoader (Registry pattern, disk cache)
4. `routeiq/graph/route_graph.py` — RouteGraph (A* pathfinding, Strategy pattern)
5. `routeiq/graph/poi_finder.py` — POIFinder (Shapely buffer spatial join, Pipeline pattern)
6. `routeiq/graph/__init__.py` — re-exports all five symbols
7. `tests/test_graph_loader.py` — mocked unit tests
8. `tests/test_route_graph.py` — synthetic graph unit tests
9. `tests/test_poi_finder.py` — mock GeoDataFrame unit tests
10. `day1_verify.py` — end-to-end verification, saves day1_map.html
11. Update `.gitignore` — add `cache/` and `day1_map.html`

### Full implementation details
See: `docs/Graph-Foundation-Implementation.md`

---

## Key implementation gotchas (don't forget these)

| Gotcha | Detail |
|---|---|
| OSMnx bbox order | `bbox=(west, south, east, north)` — OSMnx 2.x uses this order |
| nearest_nodes arg order | `ox.distance.nearest_nodes(G, X=lon, Y=lat)` — X is longitude, Y is latitude |
| Shapely coord order | `LineString([(lon, lat), ...])` — Shapely uses (x=lon, y=lat) |
| Path weight | Use `nx.path_weight(G, nodes, weight="length")` not manual sum — handles MultiDiGraph |
| POI name missing | OSM features often lack "name" tag — check for NaN, skip those rows |
| Graph load time | First run ~2-5 min (downloads ~100MB). Cache at `./cache/graphs/`. Subsequent runs instant. |

---

## Current file state

```
routeiq/
  graph/__init__.py           empty — ready for Day 1
  routing/__init__.py         empty — Day 2
  rag/__init__.py             empty — Day 3
  insights/
    prompts/                  DONE — system, query_parser, narrative, fallback
    examples/                 DONE — query_parser_examples.py
  facade.py                   does not exist yet
  pipeline.py                 does not exist yet
tests/__init__.py             empty — no test files yet
day1_verify.py                does not exist yet
docs/
  plan-day1.md                architecture decisions (Day 1 context)
  Graph-Foundation-Implementation.md  detailed step-by-step plan
  handoff-session-2.md        this file
  Architecture-and-Design-Decisions.md  all decisions with rationale (reference doc)
  Graph-Foundation-Implementation.md    Day 1 step-by-step implementation plan
prompts.md                    prompt log (3 entries from session 1)
requirements.txt              osmnx>=2.0 pinned, langgraph added
CLAUDE.md                     full conventions, updated day plan, prompt conventions
.claude/commands/             new-prompt, bump-prompt, log-prompt
```

---

## Conventions reminder

- One class per file, filename = snake_case of class name
- One-line docstring: what it IS + pattern: `"""Loads OSM graphs (Registry pattern)."""`
- Import from sub-package root only: `from routeiq.graph import RouteGraph`
- DI: graph injected into RouteGraph, never fetched internally
- Run `python3 -m pytest tests/ -v` before reporting any work done
- Log meaningful prompts to `prompts.md` after each session
