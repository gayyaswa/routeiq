# RouteIQ — Prompt Log

Running log of every prompt used across all sessions.
Format: Prompt → What it produced → Key observation

---

## Day 1 — Project setup and brainstorming

**Prompt:** Brainstorm a new AI project that covers RAG, Graph RAG, Evals, Observability,
and Fine-tuning. Background: navigation/pathfinding domain expertise, coming from a
one-week vibe coding intro project (Stock Portfolio Risk Analyzer).
→ Produced: RouteIQ concept — scenic route intelligence using Graph RAG over OSM road network
→ Key observation: Road networks are graphs. Pathfinding expertise becomes the Graph RAG
retrieval strategy. This is a genuine algorithmic advantage most LLM practitioners don't have.

**Prompt:** Scope down to one week, Graph RAG + RAG only, scenic route use case with
places people usually visit.
→ Produced: 5-day plan — OSMnx + NetworkX graph, ChromaDB RAG, Claude narrative generation
→ Key observation: Removing Neo4j and using NetworkX in-memory is the right call for Week 1.
Zero infra overhead means more time on the interesting Graph RAG logic.

**Prompt:** Create the new repo, carry over conventions from Portfolio app but tech-stack agnostic.
→ Produced: routeiq/ repo with CLAUDE.md, package skeleton, requirements.txt
→ Key observation: Conventions that are worth carrying are architectural (patterns, DI, one
class per file) not framework-specific. Streamlit constraints stay in the Portfolio app.
